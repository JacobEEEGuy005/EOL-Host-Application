from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import threading
import json
import logging
from typing import Set
from contextlib import asynccontextmanager

from backend.adapters.sim import SimAdapter
from backend.adapters.interface import Frame as AdapterFrame
import cantools

# Configure logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler: start SimAdapter reader thread and broadcaster task.

    This replaces the deprecated @app.on_event startup/shutdown handlers.
    """
    # queue for passing frames from blocking thread into async broadcaster
    frame_queue: asyncio.Queue = asyncio.Queue()
    clients: Set[WebSocket] = set()

    # start sim adapter and reader thread
    sim = SimAdapter()
    sim.open()

    loop = asyncio.get_event_loop()
    reader_thread = threading.Thread(target=_sim_reader_loop, args=(loop, frame_queue, sim), daemon=True)
    reader_thread.start()

    # start broadcaster async task
    broadcaster = asyncio.create_task(_broadcaster_task(frame_queue, clients))

    # store in app.state for shutdown/endpoint access
    app.state.sim = sim
    app.state.frame_queue = frame_queue
    app.state.clients = clients
    app.state._reader_thread = reader_thread
    app.state._broadcaster = broadcaster

    # Load persisted DBC files (Stage-2 persistence) using dbc_store helpers
    try:
        from backend.api.dbc_store import load_all_dbcs

        try:
            app.state.dbcs = load_all_dbcs()
            logger.info(f"Loaded {len(app.state.dbcs)} persisted DBC files")
        except Exception as e:
            logger.warning(f"Failed to load persisted DBCs: {e}", exc_info=True)
            app.state.dbcs = {}
    except Exception as e:
        # If the store helpers aren't available for any reason, fall back to empty dict
        logger.debug(f"DBC store module not available: {e}")
        try:
            app.state.dbcs = {}
        except Exception:
            pass

    try:
        yield
    finally:
        # Clean up on shutdown
        logger.info("Shutting down adapter and cleanup...")
        try:
            sim.close()
        except Exception as e:
            logger.warning(f"Error closing adapter: {e}", exc_info=True)
        try:
            await frame_queue.put(None)
        except Exception as e:
            logger.warning(f"Error signaling shutdown to frame queue: {e}", exc_info=True)
        try:
            await broadcaster
        except Exception as e:
            logger.warning(f"Error awaiting broadcaster task: {e}", exc_info=True)


app = FastAPI(title="EOL Host Backend", lifespan=lifespan)

# Allow local static server or other local origins to call the API during dev/testing.
if os.environ.get("ENV", "development") in ("development", "test"):
    app.add_middleware(
        CORSMiddleware,
        # allow common dev ports used by Vite and other local servers
        allow_origins=[
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )


@app.get("/api/health")
def health():
    """Simple health endpoint for Stage 1 smoke tests."""
    return {"status": "ok", "service": "eol-host-backend", "version": "0.1-stage1"}


@app.get("/")
def index():
    """Serve frontend index.html if present (production build), otherwise return a simple HTML page."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    index_path = os.path.join(repo_root, "frontend", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<html><body><h1>EOL Host Backend</h1><p>Frontend not built.</p></body></html>")


# Only register the /ws_test.html endpoint in development mode
if os.environ.get("ENV", "development") == "development":
    @app.get("/ws_test.html")
    def serve_ws_test():
        """Serve the local `frontend/ws_test.html` test page when present.

        This makes local testing simple (single origin) so the page can POST to
        `/api/send-frame` without CORS preflight issues.
        """
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        test_path = os.path.join(repo_root, "frontend", "ws_test.html")
        if os.path.exists(test_path):
            return FileResponse(test_path, media_type="text/html")
        raise HTTPException(status_code=404, detail="ws_test.html not found")


# --- WebSocket frames streaming (Stage 1 simulated publisher) -----------------
# This implements a minimal broadcaster that consumes frames from a SimAdapter
# running in a background thread and forwards them to connected WebSocket clients.


# Global structures stored on app.state in startup
async def _broadcaster_task(frame_queue: asyncio.Queue, clients: Set[WebSocket]):
    """Async task that consumes frames from frame_queue and broadcasts to clients."""
    while True:
        frame = await frame_queue.get()
        if frame is None:
            # shutdown signal
            break
        payload = json.dumps({
            "can_id": frame.can_id,
            "data": frame.data.hex(),
            "timestamp": frame.timestamp,
        })
        # send to all clients (remove any that error)
        to_remove = []
        for ws in list(clients):
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.debug(f"WebSocket send error, removing client: {e}")
                to_remove.append(ws)
        for ws in to_remove:
            try:
                clients.remove(ws)
            except KeyError:
                pass


def _sim_reader_loop(loop: asyncio.AbstractEventLoop, frame_queue: asyncio.Queue, sim: SimAdapter):
    """Blocking thread loop: reads from sim.iter_recv() and enqueues frames into the asyncio queue."""
    try:
        for frame in sim.iter_recv():
            # marshal frame into a simple dict-like object (we enqueue the Frame itself)
            loop.call_soon_threadsafe(frame_queue.put_nowait, frame)
    except Exception as e:
        # on any thread error, signal shutdown
        logger.error(f"Sim reader loop error: {e}", exc_info=True)
        try:
            loop.call_soon_threadsafe(frame_queue.put_nowait, None)
        except Exception as shutdown_err:
            logger.error(f"Failed to signal shutdown: {shutdown_err}", exc_info=True)


# Lifespan handling implemented above; startup/shutdown events removed to
# avoid DeprecationWarning from FastAPI.


@app.websocket("/ws/frames")
async def websocket_frames(ws: WebSocket):
    """WebSocket endpoint that streams incoming frames to connected clients.

    The endpoint accepts a connection and then the server pushes frames as they
    arrive from the SimAdapter. Clients receive JSON messages with fields:
      { can_id: int, data: hex-string, timestamp: float|null }
    """
    await ws.accept()
    clients: Set[WebSocket] = app.state.clients
    clients.add(ws)
    try:
        # keep the connection open until client disconnects
        while True:
            # await a ping from client or wait for disconnect; use receive to detect close
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception as e:
                # ignore non-disconnect errors and continue
                logger.debug(f"WebSocket receive error (non-fatal): {e}")
                await asyncio.sleep(0.1)
    finally:
        try:
            clients.remove(ws)
            logger.debug("WebSocket client disconnected and removed")
        except Exception as e:
            logger.debug(f"Error removing WebSocket client: {e}")



@app.post("/api/send-frame")
async def api_send_frame(payload: dict):
    """Send a frame through the SimAdapter (helpful for local testing).

    Payload: { "can_id": int, "data": "hexstring" }
    """
    can_id = payload.get("can_id")
    data_hex = payload.get("data")
    if can_id is None or data_hex is None:
        raise HTTPException(status_code=400, detail="can_id and data are required")
    
    # Validate CAN ID range (standard CAN: 0-0x7FF, extended: 0-0x1FFFFFFF)
    try:
        can_id = int(can_id)
        if not (0 <= can_id <= 0x1FFFFFFF):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid CAN ID: {can_id}. Must be between 0 and 0x1FFFFFFF"
            )
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid CAN ID format: {can_id}")
    
    # Validate and parse hex data
    try:
        data = bytes.fromhex(data_hex.replace(' ', '').replace('-', ''))
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid hex data format: {data_hex[:50]}")
        raise HTTPException(status_code=400, detail=f"data must be a valid hex string: {e}")
    
    # Validate data length (CAN frame max 8 bytes for classic CAN)
    if len(data) > 8:
        logger.warning(f"Data length {len(data)} exceeds CAN max (8 bytes)")
        raise HTTPException(
            status_code=400, 
            detail=f"Data length {len(data)} exceeds maximum CAN frame size (8 bytes)"
        )

    sim: SimAdapter = getattr(app.state, "sim", None)
    if sim is None:
        raise HTTPException(status_code=503, detail="Sim adapter not available")

    # create Adapter Frame and send (SimAdapter loopbacks to recv/iter_recv)
    f = AdapterFrame(can_id=can_id, data=data)
    try:
        sim.send(f)
        logger.debug(f"Sent frame: can_id=0x{can_id:X}, data={data.hex()}")
    except Exception as e:
        logger.error(f"Failed to send frame: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    # ensure a copy is available for direct recv() callers (tests may read sim.recv)
    try:
        # prefer explicit loopback if available
        if hasattr(sim, "loopback"):
            sim.loopback(f)
        else:
            # best-effort fallback
            sim.send(f)
    except Exception as e:
        logger.debug(f"Loopback operation failed (non-fatal): {e}")
    # Also enqueue into the async frame_queue if present so tests / websocket
    # broadcaster observers will reliably see the frame even if a reader
    # thread consumes the SimAdapter queue first. This is a low-risk, test-
    # friendly enhancement that mirrors the loopback for async consumers.
    try:
        frame_queue = getattr(app.state, "frame_queue", None)
        if frame_queue is not None:
            # frame_queue is an asyncio.Queue; we're in an async handler so await
            await frame_queue.put(f)
    except Exception as e:
        logger.debug(f"Failed to enqueue frame to frame_queue (non-fatal): {e}")
    return {"status": "ok"}


# Stage-2: DBC router (scaffold)
try:
    # import locally so Stage-1 consumers without the file won't break imports
    from backend.api import dbc as _dbc_module
    app.include_router(_dbc_module.router)
except Exception:
    # If the router isn't present or import fails, don't prevent the app from starting.
    pass

# metrics router (small and safe to include)
try:
    from backend.api import metrics as _metrics_module
    app.include_router(_metrics_module.router)
except Exception:
    # non-fatal: metrics endpoint not required for Stage-1
    pass

