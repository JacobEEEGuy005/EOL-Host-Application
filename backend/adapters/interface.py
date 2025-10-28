from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Iterable, Protocol


@dataclass
class Frame:
    """Simple CAN frame representation for adapters in Stage 1 tests."""
    can_id: int
    data: bytes
    timestamp: Optional[float] = None


class Adapter(Protocol):
    """Adapter interface that all CAN adapters should implement."""

    def open(self) -> None:
        ...

    def close(self) -> None:
        ...

    def send(self, frame: Frame) -> None:
        ...

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        """Receive a single frame, or None on timeout."""
        ...

    def iter_recv(self) -> Iterable[Frame]:
        """Return an iterable that yields frames as they arrive."""
        ...
