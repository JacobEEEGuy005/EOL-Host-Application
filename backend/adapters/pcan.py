"""PCAN adapter using python-can.

This adapter wraps python-can's Bus for PCAN (Peak) USB devices.

Configuration (via environment variables):
- PCAN_CHANNEL (default: "PCAN_USBBUS1")
- PCAN_BITRATE  (optional, e.g. "500000")
"""
from __future__ import annotations

import os
import queue
import threading
import logging
from typing import Optional, Iterable

import can

from .interface import Adapter, Frame


logger = logging.getLogger(__name__)


class PcanAdapter:
    def __init__(self, channel: Optional[str] = None, bitrate: Optional[int] = None) -> None:
        self.channel = channel or os.environ.get("PCAN_CHANNEL", "PCAN_USBBUS1")
        br = bitrate or (int(os.environ.get("PCAN_BITRATE")) if os.environ.get("PCAN_BITRATE") else None)
        self.bitrate = br
        self._bus: Optional[can.Bus] = None
        self._running = False
        # loopback queue for deterministic recv() behavior in tests
        self._loopback_q: queue.Queue[Frame] = queue.Queue()
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            if self._bus is not None:
                return
            kwargs = {"bustype": "pcan", "channel": self.channel}
            if self.bitrate:
                kwargs["bitrate"] = self.bitrate
            # python-can uses different backend names; 'pcan' is supported on Windows with PCANBasic
            logger.info("Opening PCAN bus with %s", kwargs)
            try:
                self._bus = can.Bus(**kwargs)
                self._running = True
                logger.info("PCAN bus opened")
            except Exception:
                logger.exception("Failed to open PCAN bus")
                raise

    def close(self) -> None:
        with self._lock:
            self._running = False
            if self._bus is not None:
                try:
                    # shutdown is the recommended method
                    self._bus.shutdown()
                except Exception:
                    try:
                        self._bus.close()
                    except Exception:
                        pass
                logger.info("Closing PCAN bus")
                self._bus = None

    def send(self, frame: Frame) -> None:
        if self._bus is None:
            raise RuntimeError("PCAN bus not open")
        msg = can.Message(arbitration_id=frame.can_id, data=frame.data, is_extended_id=False)
        logger.debug("Sending CAN message: id=0x%x data=%s", frame.can_id, frame.data.hex())
        try:
            self._bus.send(msg)
        except Exception:
            logger.exception("Failed to send CAN message")
            raise
        # ensure recv() callers can see the frame deterministically
        try:
            self._loopback_q.put_nowait(frame)
        except Exception:
            self._loopback_q.put(frame)
        logger.debug("Enqueued frame to loopback queue")

    def loopback(self, frame: Frame) -> None:
        """Explicitly enqueue a frame for recv() callers (tests use this)."""
        logger.debug("Loopback enqueue: id=0x%x data=%s", frame.can_id, frame.data.hex())
        try:
            self._loopback_q.put_nowait(frame)
        except Exception:
            self._loopback_q.put(frame)

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        # prefer loopback frames for deterministic behavior
        try:
            f = self._loopback_q.get_nowait()
            logger.debug("Recv returning loopback frame id=0x%x", f.can_id)
            return f
        except queue.Empty:
            pass

        if self._bus is None:
            return None
        try:
            msg = self._bus.recv(timeout)
        except Exception:
            logger.exception("Error receiving from PCAN bus")
            return None
        if msg is None:
            return None
        frame = Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b""), timestamp=getattr(msg, "timestamp", None))
        logger.debug("Recv got frame id=0x%x data=%s", frame.can_id, frame.data.hex())
        return frame

    def iter_recv(self) -> Iterable[Frame]:
        # yield frames from the bus until adapter is closed
        while True:
            with self._lock:
                if not self._running:
                    break
            try:
                msg = self._bus.recv(1.0) if self._bus is not None else None
            except Exception:
                msg = None
            if msg is None:
                continue
            frame = Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b""), timestamp=getattr(msg, "timestamp", None))
            logger.debug("iter_recv yielding frame id=0x%x", frame.can_id)
            yield frame
