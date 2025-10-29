"""SocketCAN adapter wrapper using python-can for Linux-like systems.

This mirrors the PCAN adapter pattern but uses the 'socketcan' bustype for
machines that expose a SocketCAN interface (Linux, RPi).
"""
from __future__ import annotations

import os
import queue
import threading
import logging
from typing import Optional, Iterable, Any

import can

from .interface import Adapter, Frame
from backend import metrics


logger = logging.getLogger(__name__)


class SocketCanAdapter:
    def __init__(self, channel: Optional[str] = None) -> None:
        self.channel = channel or os.environ.get("SOCKETCAN_CHANNEL", "can0")
        # can.Bus typing is imperfect across python-can versions; use Any to avoid static type issues
        self._bus: Optional[Any] = None
        self._running = False
        self._loopback_q: queue.Queue[Frame] = queue.Queue()
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            if self._bus is not None:
                return
            kwargs = {"bustype": "socketcan", "channel": self.channel}
            logger.info("Opening SocketCAN bus %s", kwargs)
            self._bus = can.Bus(**kwargs)
            self._running = True

    def close(self) -> None:
        with self._lock:
            self._running = False
            if self._bus is not None:
                try:
                    self._bus.shutdown()
                except Exception:
                    try:
                        self._bus.close()
                    except Exception:
                        pass
                self._bus = None

    def send(self, frame: Frame) -> None:
        if self._bus is None:
            raise RuntimeError("SocketCAN bus not open")
        msg = can.Message(arbitration_id=frame.can_id, data=frame.data, is_extended_id=False)
        logger.debug("SocketCAN send id=0x%x data=%s", frame.can_id, frame.data.hex())
        self._bus.send(msg)
        # metrics
        try:
            metrics.inc("socketcan_send")
        except Exception:
            pass
        try:
            self._loopback_q.put_nowait(frame)
        except Exception:
            self._loopback_q.put(frame)

    def loopback(self, frame: Frame) -> None:
        try:
            self._loopback_q.put_nowait(frame)
        except Exception:
            self._loopback_q.put(frame)

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        try:
            f = self._loopback_q.get_nowait()
            metrics.inc("socketcan_recv")
            return f
        except queue.Empty:
            pass
        if self._bus is None:
            return None
        msg = self._bus.recv(timeout)
        if msg is None:
            return None
        frame = Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b""), timestamp=getattr(msg, "timestamp", None))
        metrics.inc("socketcan_recv")
        return frame

    def iter_recv(self) -> Iterable[Frame]:
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
            metrics.inc("socketcan_recv")
            yield frame
