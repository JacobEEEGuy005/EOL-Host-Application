import queue
import threading
import time
from typing import Optional, Iterable
from .interface import Adapter, Frame
from backend import metrics


class SimAdapter:
    """A simple in-memory simulated adapter for testing.

    Usage:
      a = SimAdapter()
      a.open()
      a.send(Frame(...))
      f = a.recv()
      a.close()
    """

    def __init__(self) -> None:
        # main queue consumed by both recv() and iter_recv()
        self._q: queue.Queue[Frame] = queue.Queue()
        # explicit loopback queue used to guarantee availability to direct
        # recv() callers even if a background reader thread consumes from
        # the main queue first.
        self._loopback_q: queue.Queue[Frame] = queue.Queue()
        self._running = False
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            self._running = True

    def close(self) -> None:
        with self._lock:
            self._running = False
        # drain queue
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break

    def send(self, frame: Frame) -> None:
        """Enqueue a frame to the receive queue to simulate loopback."""
        # simulate minor latency
        time.sleep(0.001)
        # Pad data to 8 bytes to mirror classic CAN DLC behavior
        data_bytes = bytes(frame.data) if frame.data is not None else b''
        if len(data_bytes) < 8:
            data_bytes = data_bytes + b'\x00' * (8 - len(data_bytes))
        # create a new frame object to avoid mutating caller's frame
        f = Frame(can_id=frame.can_id, data=data_bytes, timestamp=getattr(frame, 'timestamp', None))
        self._q.put(f)
        try:
            metrics.inc("sim_send")
        except Exception:
            pass

    def loopback(self, frame: Frame) -> None:
        """Explicitly enqueue a frame for loopback/receivers. Use when tests
        or external callers want to guarantee the frame is available to
        `recv()` even if other consumers are present.
        """
        # Put into both the main queue (for iter_recv/background readers)
        # and a dedicated loopback queue reserved for direct recv callers.
        try:
            self._q.put_nowait(frame)
        except Exception:
            self._q.put(frame)
        try:
            self._loopback_q.put_nowait(frame)
        except Exception:
            self._loopback_q.put(frame)
        try:
            metrics.inc("sim_loopback")
        except Exception:
            pass

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        # Prefer frames explicitly looped-back for direct recv callers so
        # tests and synchronous consumers can reliably read a frame even if
        # a background thread is also consuming from the main queue.
        try:
            f = self._loopback_q.get_nowait()
            try:
                metrics.inc("sim_recv")
            except Exception:
                pass
            # ensure loopback frames also honor filters
            if self._frame_matches_filters(f):
                return f
            # otherwise fall through to consume from the main queue
        except queue.Empty:
            pass
        try:
            # consume until timeout, skipping frames that don't match filters
            end = None if timeout is None else (time.time() + float(timeout))
            while True:
                remaining = None if end is None else max(0.0, end - time.time())
                try:
                    f = self._q.get(timeout=remaining)
                except queue.Empty:
                    return None
                if self._frame_matches_filters(f):
                    try:
                        metrics.inc("sim_recv")
                    except Exception:
                        pass
                    return f
                # else skip and continue until timeout
                if end is not None and time.time() >= end:
                    return None
                continue
        except queue.Empty:
            return None

    def iter_recv(self) -> Iterable[Frame]:
        """Yield frames until adapter is closed."""
        # Use the main queue directly for the background reader so that
        # explicit loopback frames reserved for direct recv() callers are
        # not stolen by the background thread.
        while True:
            with self._lock:
                if not self._running and self._q.empty():
                    break
            try:
                f = self._q.get(timeout=0.5)
            except queue.Empty:
                f = None
            if f is not None:
                try:
                    # honor filters by skipping non-matching frames
                    if not self._frame_matches_filters(f):
                        continue
                    metrics.inc("sim_recv")
                except Exception:
                    pass
                yield f

    def set_filters(self, filters):
        """Store filters for the simulator. Filters are honored by recv/iter_recv."""
        try:
            self._filters = list(filters) if filters is not None else None
        except Exception:
            self._filters = filters

    def _frame_matches_filters(self, frame: Frame) -> bool:
        """Return True if the given frame matches the configured filters.

        Filters are expected as dicts containing at least 'can_id' and optionally
        'can_mask' and 'extended'. If no filters are set, all frames match.
        """
        if getattr(self, '_filters', None) is None:
            return True
        try:
            for f in self._filters:
                try:
                    fid = int(f.get('can_id', 0)) if isinstance(f, dict) else int(getattr(f, 'can_id', 0))
                except Exception:
                    continue
                extended = bool(f.get('extended', False)) if isinstance(f, dict) else False
                try:
                    mask = int(f.get('can_mask')) if isinstance(f, dict) and f.get('can_mask') is not None else (0x1FFFFFFF if extended else 0x7FF)
                except Exception:
                    mask = 0x1FFFFFFF if extended else 0x7FF
                try:
                    if (int(frame.can_id) & mask) == (fid & mask):
                        return True
                except Exception:
                    continue
        except Exception:
            return True
        return False
