"""
Signal Value model for representing decoded CAN signal values.
"""
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class SignalValue:
    """Represents a decoded signal value from a CAN message.
    
    Attributes:
        signal_name: Name of the signal from DBC
        value: Decoded signal value (can be numeric, string, enum, etc.)
        message_id: CAN message ID where signal was found
        message_name: Name of the CAN message (optional)
        timestamp: Timestamp when signal value was received
        raw_data: Raw frame data bytes (optional, for debugging)
    """
    signal_name: str
    value: Any
    message_id: int
    message_name: Optional[str] = None
    timestamp: Optional[float] = None
    raw_data: Optional[bytes] = None
    
    def __post_init__(self):
        """Validate signal value data."""
        if not self.signal_name:
            raise ValueError("signal_name cannot be empty")
        if not (0 <= self.message_id <= 0x1FFFFFFF):
            raise ValueError(f"message_id out of range: 0x{self.message_id:X}")
    
    @property
    def key(self) -> str:
        """Return a cache key for this signal (message_id:signal_name)."""
        return f"{self.message_id}:{self.signal_name}"
    
    def __str__(self) -> str:
        """String representation for display."""
        return f"{self.signal_name}={self.value}"

