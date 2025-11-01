"""
CAN Frame model for representing CAN bus frames.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class CanFrame:
    """Represents a CAN bus frame with ID, data, and optional timestamp.
    
    Attributes:
        can_id: CAN identifier (0-0x1FFFFFFF for extended, 0-0x7FF for standard)
        data: Frame data bytes (up to 8 bytes for classic CAN)
        timestamp: Optional timestamp when frame was received (Unix timestamp)
    """
    can_id: int
    data: bytes
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        """Validate frame data after initialization."""
        if not isinstance(self.data, bytes):
            raise TypeError(f"data must be bytes, got {type(self.data)}")
        if len(self.data) > 8:
            raise ValueError(f"CAN data length must be <= 8 bytes, got {len(self.data)}")
        if not (0 <= self.can_id <= 0x1FFFFFFF):
            raise ValueError(f"CAN ID out of range: 0x{self.can_id:X}")
    
    @property
    def data_hex(self) -> str:
        """Return frame data as hexadecimal string."""
        return self.data.hex()
    
    @property
    def data_length(self) -> int:
        """Return frame data length."""
        return len(self.data)

