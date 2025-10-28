"""Thin shim adapter that uses python-can to talk to CL2000/csscan serial backends.

This adapter attempts to create a python-can Bus using the provided interface and
channel. For tests we default to the 'virtual' interface when available.
"""
from typing import Optional
from .interface import Adapter, Frame

try:
    import can
except Exception:  # pragma: no cover - import failure handled at runtime
    can = None


class CSSCANAdapter:
    """Adapter backed by python-can Bus. Callers should pass interface and channel.

    Example:
      a = CSSCANAdapter(interface='virtual')
      a.open()
      a.send(Frame(0x100, b"\x01"))
      f = a.recv(timeout=1.0)
      a.close()
    """

    def __init__(self, interface: str = "csscan", channel: Optional[str] = None, bitrate: int = 500000):
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self._bus: Optional["can.Bus"] = None

    def open(self) -> None:
        if can is None:
            raise RuntimeError("python-can is not installed")
        # create a Bus; channel may be None for some backends
        kwargs = {"interface": self.interface}
        if self.channel is not None:
            kwargs["channel"] = self.channel
        if self.bitrate is not None:
            kwargs["bitrate"] = self.bitrate
        # For virtual backends it's useful to receive our own messages during tests
        if self.interface == "virtual":
            kwargs["receive_own_messages"] = True
        self._bus = can.Bus(**kwargs)

    def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.shutdown()
            except Exception:
                pass
            self._bus = None

    def send(self, frame: Frame) -> None:
        if self._bus is None:
            raise RuntimeError("Bus not open")
        msg = can.Message(arbitration_id=frame.can_id, data=frame.data, is_extended_id=False)
        self._bus.send(msg)

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        if self._bus is None:
            raise RuntimeError("Bus not open")
        msg = self._bus.recv(timeout)
        if msg is None:
            return None
        return Frame(can_id=msg.arbitration_id, data=bytes(msg.data), timestamp=getattr(msg, "timestamp", None))

    def iter_recv(self):
        # simple generator using recv
        while True:
            f = self.recv(timeout=0.5)
            if f is None:
                continue
            yield f
