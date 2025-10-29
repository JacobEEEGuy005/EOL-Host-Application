from __future__ import annotations
import threading
import time
from typing import Optional, Iterable

try:
    import can
except Exception:
    can = None

from .interface import Adapter, Frame


class PythonCanAdapter:
    """Wrapper around python-can Bus that implements the project's Adapter protocol.

    The adapter accepts and returns `backend.adapters.interface.Frame` objects so it
    can be used by the existing GUI and test runner without changes.
    """

    def __init__(self, channel: str = 'virtual', bitrate: Optional[int] = None, interface: Optional[str] = None):
        self.channel = channel
        self.bitrate = bitrate
        self.interface = interface
        self._bus: Optional[object] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._out_queue: list[Frame] = []
        self._lock = threading.Lock()

    def open(self) -> None:
        if can is None:
            raise RuntimeError('python-can library not available')
        kwargs = {}
        if self.bitrate is not None:
            try:
                kwargs['bitrate'] = int(self.bitrate)
            except Exception:
                pass
        # interface may be None for python-can to auto-select default backends
        if self.interface:
            self._bus = can.Bus(channel=self.channel, interface=self.interface, **kwargs)
        else:
            self._bus = can.Bus(channel=self.channel, **kwargs)

        self._stop.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._recv_thread:
            self._recv_thread.join(timeout=1.0)
        if self._bus is not None:
            try:
                # python-can API provides shutdown()
                self._bus.shutdown()
            except Exception:
                try:
                    self._bus.stop()
                except Exception:
                    pass
            self._bus = None

    def send(self, frame: Frame) -> None:
        if self._bus is None:
            raise RuntimeError('Bus not open')
        # build can.Message
        try:
            msg = can.Message(arbitration_id=int(frame.can_id), data=bytes(frame.data), is_extended_id=False)
            self._bus.send(msg)
        except Exception:
            # best-effort: ignore send errors here and allow caller to handle
            raise

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        if self._bus is None:
            return None
        try:
            msg = self._bus.recv(timeout=timeout)
            if msg is None:
                return None
            return Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b''), timestamp=getattr(msg, 'timestamp', time.time()))
        except Exception:
            return None

    def iter_recv(self) -> Iterable[Frame]:
        # Yield frames from bus.recv in a loop until stopped
        while not self._stop.is_set():
            try:
                msg = self._bus.recv(timeout=0.5) if self._bus is not None else None
                if msg is None:
                    continue
                yield Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b''), timestamp=getattr(msg, 'timestamp', time.time()))
            except Exception:
                # sleep briefly to avoid busy-loop on persistent errors
                time.sleep(0.1)
                continue
