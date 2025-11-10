"""
Signal Service for decoding CAN signals and managing signal value cache.

This service handles signal decoding from CAN frames, caching of signal values,
and retrieval of latest signal values for test execution.
"""
import time
import logging
from typing import Optional, Tuple, Any, Dict
from backend.adapters.interface import Frame

from host_gui.services.dbc_service import DbcService
from host_gui.models.signal_value import SignalValue

# Import signal processing constants
try:
    from host_gui.constants import ADC_A3_GAIN_FACTOR
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Failed to import ADC_A3_GAIN_FACTOR from constants, using default value 1.0")
    ADC_A3_GAIN_FACTOR = 1.0

try:
    from host_gui.exceptions import SignalDecodeError
except ImportError:
    SignalDecodeError = ValueError

logger = logging.getLogger(__name__)


class SignalService:
    """Service for decoding CAN signals and managing signal value cache.
    
    This service provides:
    - Decoding frames into signal values using DBC
    - Caching latest signal values for quick lookup
    - Retrieving latest signal values by message ID and signal name
    - Handling signal value formatting (numeric vs string)
    
    Attributes:
        dbc_service: Reference to DbcService for DBC operations
        _signal_values: Cache of latest signal values
                       Key: "message_id:signal_name" -> (timestamp, value)
    """
    
    def __init__(self, dbc_service: DbcService):
        """Initialize the signal service.
        
        Args:
            dbc_service: DbcService instance for DBC operations
        """
        self.dbc_service = dbc_service
        self._signal_values: Dict[str, Tuple[float, Any]] = {}
    
    def decode_frame(self, frame: Frame) -> list[SignalValue]:
        """Decode a CAN frame into signal values.
        
        Args:
            frame: CAN frame with can_id, data, and optional timestamp
            
        Returns:
            List of SignalValue objects (empty if decoding fails or no DBC loaded)
        """
        if not self.dbc_service.is_loaded():
            logger.debug("SignalService.decode_frame: DBC not loaded in service")
            return []
        
        try:
            can_id = int(getattr(frame, 'can_id', 0))
        except (ValueError, TypeError) as e:
            logger.debug(f"SignalService.decode_frame: Invalid CAN ID: {e}")
            return []
        
        # Find message
        message = self.dbc_service.find_message_by_id(can_id)
        if message is None:
            logger.debug(f"SignalService.decode_frame: No message found for CAN ID 0x{can_id:X}")
            return []
        
        # Get frame data
        raw_data = getattr(frame, 'data', b'')
        if isinstance(raw_data, str):
            try:
                raw_data = bytes.fromhex(raw_data)
            except (ValueError, TypeError) as e:
                logger.debug(f"SignalService.decode_frame: Invalid hex data: {e}")
                raw_data = b''
        
        if not raw_data:
            logger.debug(f"SignalService.decode_frame: Empty frame data for CAN ID 0x{can_id:X}")
            return []
        
        # Decode message
        try:
            decoded = self.dbc_service.decode_message(message, raw_data)
        except ValueError as e:
            logger.warning(f"SignalService.decode_frame: Failed to decode message 0x{can_id:X}: {e}")
            # Raise SignalDecodeError but allow caller to handle gracefully
            raise SignalDecodeError(f"Failed to decode CAN message 0x{can_id:X}: {e}",
                                  can_id=can_id, data=raw_data, original_error=e)
        except Exception as e:
            logger.error(f"SignalService.decode_frame: Unexpected error decoding 0x{can_id:X}: {e}", exc_info=True)
            raise SignalDecodeError(f"Unexpected error decoding CAN message 0x{can_id:X}: {e}",
                                  can_id=can_id, data=raw_data, original_error=e)
        
        if not decoded:
            logger.warning(f"SignalService.decode_frame: Decoded message 0x{can_id:X} returned empty dict")
            return []
        
        # Create SignalValue objects and update cache
        # Validate and use frame timestamp, or fall back to current time
        frame_timestamp = getattr(frame, 'timestamp', None)
        current_time = time.time()
        
        # Only use frame timestamp if it's explicitly provided and reasonable
        # Timestamps should be Unix epoch seconds (typically > 1e9 for dates after 2001)
        # and not too far in the future (within 30 years)
        if frame_timestamp is not None:
            # Validate timestamp is reasonable (Unix epoch range, not relative time)
            # Valid Unix timestamps: 0 to ~2147483647 (year 2038), but we'll check for reasonable range
            # For 2025: timestamps should be ~1700000000-1800000000
            # If timestamp is too small (< 1e9) or negative, it's likely relative time or invalid
            # Validate timestamp is in reasonable Unix epoch range (after year 2001, within 30 years future)
            # Small values (< 1e9) likely indicate relative time, milliseconds, or other invalid format
            if frame_timestamp > 1e9 and frame_timestamp < current_time + (86400 * 365 * 30):
                timestamp = frame_timestamp
            else:
                # Timestamp appears invalid (relative time, microseconds, or wrong format)
                # Use current decode time instead to ensure accurate timestamps
                age_sec = current_time - frame_timestamp if frame_timestamp > 0 else None
                logger.debug(
                    f"Frame timestamp validation failed: frame_ts={frame_timestamp}, "
                    f"current_ts={current_time}, using decode time instead. "
                    f"(frame_ts seems {'relative/invalid' if frame_timestamp < 1e9 else 'too far in future'})"
                )
                timestamp = current_time
        else:
            # No timestamp from frame, use current decode time
            timestamp = current_time
        
        signal_values = []
        message_name = getattr(message, 'name', None)
        
        logger.debug(f"SignalService.decode_frame: Decoded {len(decoded)} signals from message 0x{can_id:X} ({message_name or 'unknown'})")
        
        for signal_name, value in decoded.items():
            # Try to get numeric value (prefer numeric for test comparisons)
            numeric_value = self._extract_numeric_value(message, raw_data, signal_name, value)
            
            # Apply signal-specific processing (e.g., gain factors)
            processed_value = self._apply_signal_processing(signal_name, numeric_value if numeric_value is not None else value)
            
            # Create SignalValue with processed value
            signal_value = SignalValue(
                signal_name=signal_name,
                value=processed_value,
                message_id=can_id,
                message_name=message_name,
                timestamp=timestamp,
                raw_data=raw_data
            )
            
            signal_values.append(signal_value)
            
            # Update cache with processed value
            key = signal_value.key
            self._signal_values[key] = (timestamp, signal_value.value)
            logger.debug(f"SignalService: Cached signal {key} = {signal_value.value}")
        
        return signal_values
    
    def get_latest_signal(self, message_id: Optional[int], signal_name: Optional[str]) -> Tuple[Optional[float], Optional[Any]]:
        """Get the latest cached value for a signal.
        
        Args:
            message_id: CAN message ID (or None)
            signal_name: Signal name (or None)
            
        Returns:
            Tuple of (timestamp, value) or (None, None) if not found
            Note: Signal-specific processing (e.g., gain factors) is already applied to cached values
        """
        if message_id is None or signal_name is None:
            return (None, None)
        
        key = f"{message_id}:{signal_name}"
        return self._signal_values.get(key, (None, None))
    
    def get_all_signals_for_message(self, message_id: int) -> Dict[str, Tuple[float, Any]]:
        """Get all cached signals for a specific message.
        
        Args:
            message_id: CAN message ID
            
        Returns:
            Dictionary mapping signal_name -> (timestamp, value)
        """
        prefix = f"{message_id}:"
        result = {}
        for key, (ts, val) in self._signal_values.items():
            if key.startswith(prefix):
                signal_name = key[len(prefix):]
                result[signal_name] = (ts, val)
        return result
    
    def clear_cache(self):
        """Clear all cached signal values."""
        self._signal_values.clear()
        logger.debug("Cleared signal value cache")
    
    def clear_cache_for_message(self, message_id: int):
        """Clear cached signals for a specific message.
        
        Args:
            message_id: CAN message ID
        """
        prefix = f"{message_id}:"
        keys_to_remove = [key for key in self._signal_values.keys() if key.startswith(prefix)]
        for key in keys_to_remove:
            del self._signal_values[key]
        logger.debug(f"Cleared cache for message 0x{message_id:X}")
    
    def _apply_signal_processing(self, signal_name: str, value: Any) -> Any:
        """Apply signal-specific processing (e.g., gain factors) to signal values.
        
        Args:
            signal_name: Name of the signal
            value: Signal value to process
            
        Returns:
            Processed signal value
        """
        # Apply ADC_A3_mV gain factor
        if signal_name == 'ADC_A3_mV' and value is not None:
            try:
                processed = float(value) * ADC_A3_GAIN_FACTOR
                logger.debug(f"SignalService: Applied gain factor {ADC_A3_GAIN_FACTOR} to {signal_name}: {value} -> {processed}")
                return processed
            except (ValueError, TypeError):
                # If conversion fails, return original value
                logger.debug(f"SignalService: Could not apply gain factor to {signal_name} (value: {value})")
                return value
        
        return value
    
    def _extract_numeric_value(self, message: Any, raw_data: bytes, signal_name: str, decoded_value: Any) -> Optional[Any]:
        """Extract numeric value from decoded signal, preferring raw numeric over enum labels.
        
        Args:
            message: Message object from cantools
            raw_data: Raw frame data bytes
            signal_name: Name of the signal
            decoded_value: Decoded value (may be enum label string)
            
        Returns:
            Numeric value if possible, otherwise returns decoded_value unchanged
        """
        # If already numeric, return as-is
        if isinstance(decoded_value, (int, float)):
            return decoded_value
        
        # Try to decode without choices to get raw numeric value
        try:
            # Some cantools versions support decode_choices parameter
            numeric_decoded = message.decode(raw_data, decode_choices=False)
            if signal_name in numeric_decoded:
                numeric_val = numeric_decoded[signal_name]
                if isinstance(numeric_val, (int, float)):
                    return numeric_val
        except (TypeError, AttributeError):
            # decode doesn't support decode_choices parameter
            pass
        except Exception:
            # Other decoding errors
            pass
        
        # Try to coerce string to int if it's a digit string
        if isinstance(decoded_value, str):
            try:
                if decoded_value.isdigit() or (decoded_value.startswith('-') and decoded_value[1:].isdigit()):
                    return int(decoded_value)
            except (ValueError, AttributeError):
                pass
        
        # Return original value
        return decoded_value
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about the signal cache.
        
        Returns:
            Dictionary with cache statistics (total_signals, unique_messages, etc.)
        """
        total_signals = len(self._signal_values)
        
        # Count unique messages
        message_ids = set()
        for key in self._signal_values.keys():
            try:
                msg_id = int(key.split(':')[0])
                message_ids.add(msg_id)
            except (ValueError, IndexError):
                pass
        
        return {
            'total_signals': total_signals,
            'unique_messages': len(message_ids),
            'cache_size_bytes': total_signals * 32  # Rough estimate
        }

