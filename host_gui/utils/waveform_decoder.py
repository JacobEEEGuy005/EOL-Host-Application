"""
Waveform decoder for oscilloscope data.

This module provides classes for decoding binary waveform data from oscilloscopes,
specifically supporting the WAVEDESC format used by Siglent oscilloscopes.
"""
import struct
import logging
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False


class WaveformDecoder:
    """Simplified waveform decoder for oscilloscope data.
    
    This class decodes binary waveform data from oscilloscope C1:WF? ALL command.
    It parses the WAVEDESC descriptor and data array to extract voltage/time values.
    """
    
    # Key offsets in WAVEDESC block
    DESCRIPTOR_NAME_OFFSET = 0
    TEMPLATE_NAME_OFFSET = 16
    WAVE_DESCRIPTOR_OFFSET = 36
    USER_TEXT_OFFSET = 40
    TRIGTIME_ARRAY_OFFSET = 44
    RIS_TIME_ARRAY_OFFSET = 52
    WAVE_ARRAY_1_OFFSET = 60
    WAVE_ARRAY_COUNT_OFFSET = 116
    COMM_TYPE_OFFSET = 32
    COMM_ORDER_OFFSET = 34
    VERTICAL_GAIN_OFFSET = 156
    VERTICAL_OFFSET_OFFSET = 160
    HORIZ_INTERVAL_OFFSET = 176
    HORIZ_OFFSET_OFFSET = 180
    
    COMM_TYPE_BYTE = 0
    COMM_TYPE_WORD = 1
    
    def __init__(self, waveform_data: bytes):
        """Initialize decoder with waveform binary data.
        
        Args:
            waveform_data: Raw binary data from C1:WF? ALL command
        """
        self.waveform_data = waveform_data
        self.wavedesc_start = 0
        
        # Find WAVEDESC start if not at beginning
        if not waveform_data[:8].startswith(b'WAVEDESC'):
            pos = waveform_data.find(b'WAVEDESC')
            if pos >= 0:
                self.wavedesc_start = pos
    
    def decode(self, vertical_gain: Optional[float] = None, vertical_offset: Optional[float] = None) -> Tuple[Dict, List[float], List[float]]:
        """Decode waveform data.
        
        Args:
            vertical_gain: Optional vertical gain from C1:VDIV? command
            vertical_offset: Optional vertical offset from C1:OFST? command
            
        Returns:
            Tuple of (descriptor_dict, time_values, voltage_values)
        """
        if len(self.waveform_data) < self.wavedesc_start + 400:
            raise ValueError(f"Waveform data too short: {len(self.waveform_data)} bytes")
        
        # Parse WAVEDESC block
        descriptor = self._parse_wavedesc()
        
        # Determine data format
        comm_type = descriptor['COMM_TYPE']
        if comm_type == self.COMM_TYPE_BYTE:
            data_format = 'b'  # signed byte
            data_size = 1
        elif comm_type == self.COMM_TYPE_WORD:
            data_format = 'h'  # signed short (16-bit)
            data_size = 2
        else:
            raise ValueError(f"Unsupported COMM_TYPE: {comm_type}")
        
        # Calculate data array start position
        wave_descriptor_length = descriptor['WAVE_DESCRIPTOR']
        user_text_length = descriptor['USER_TEXT']
        data_array_start = (self.wavedesc_start + wave_descriptor_length + user_text_length)
        
        # Extract data array
        wave_array_1_length = descriptor['WAVE_ARRAY_1']
        wave_array_count = descriptor['WAVE_ARRAY_COUNT']
        actual_data_length = wave_array_count * data_size
        available_data = len(self.waveform_data) - data_array_start
        data_length_to_use = min(wave_array_1_length, actual_data_length, available_data)
        
        if data_array_start > len(self.waveform_data) or data_length_to_use <= 0:
            raise ValueError(f"Invalid data array: start={data_array_start}, length={data_length_to_use}")
        
        if data_length_to_use < actual_data_length:
            wave_array_count = data_length_to_use // data_size
        
        data_array_bytes = self.waveform_data[data_array_start:data_array_start + data_length_to_use]
        
        # Unpack data points
        num_points = min(wave_array_count, len(data_array_bytes) // data_size)
        raw_data_points = struct.unpack(f'<{num_points}{data_format}', 
                                       data_array_bytes[:num_points * data_size])
        
        # Use provided values from C{channel}:VDIV? and C{channel}:OFST? if available,
        # otherwise fall back to descriptor values
        if vertical_gain is None:
            vertical_gain = descriptor['VERTICAL_GAIN']
            logger.debug(f"Using VERTICAL_GAIN from descriptor: {vertical_gain}")
        else:
            logger.debug(f"Using vertical gain from VDIV? query: {vertical_gain}")
        
        if vertical_offset is None:
            vertical_offset = descriptor['VERTICAL_OFFSET']
            logger.debug(f"Using VERTICAL_OFFSET from descriptor: {vertical_offset}")
        else:
            logger.debug(f"Using vertical offset from OFST? query: {vertical_offset}")
        
        # Convert raw values to physical voltage values using:
        # voltage = (vertical_gain * raw_value) / 25.0 - vertical_offset
        # where:
        # - vertical_gain is from C{channel}:VDIV? (V/div) or descriptor
        # - vertical_offset is from C{channel}:OFST? (V) or descriptor
        # - raw_value is the signed integer from the waveform data
        # - The /25.0 factor converts the raw value to the correct scale
        if numpy_available:
            raw_data_array = np.array(raw_data_points, dtype=np.float32)
            voltage_values = ((vertical_gain * raw_data_array) / 25.0 - vertical_offset).tolist()
        else:
            voltage_values = [(vertical_gain * dp) / 25.0 - vertical_offset for dp in raw_data_points]
        
        # Calculate time values
        horiz_interval = descriptor['HORIZ_INTERVAL']
        horiz_offset = descriptor['HORIZ_OFFSET']
        
        if numpy_available:
            time_values = (np.arange(num_points, dtype=np.float64) * horiz_interval + horiz_offset).tolist()
        else:
            time_values = [(i * horiz_interval) + horiz_offset for i in range(num_points)]
        
        return descriptor, time_values, voltage_values
    
    def _parse_wavedesc(self) -> Dict:
        """Parse WAVEDESC block from waveform data.
        
        Returns:
            Dictionary with waveform descriptor fields
        """
        descriptor = {}
        
        # WAVE_DESCRIPTOR (long, 4 bytes at offset 36)
        descriptor['WAVE_DESCRIPTOR'] = struct.unpack('<I',
            self.waveform_data[self.wavedesc_start + self.WAVE_DESCRIPTOR_OFFSET:
                              self.wavedesc_start + self.WAVE_DESCRIPTOR_OFFSET + 4])[0]
        
        # USER_TEXT (long, 4 bytes at offset 40)
        descriptor['USER_TEXT'] = struct.unpack('<I',
            self.waveform_data[self.wavedesc_start + self.USER_TEXT_OFFSET:
                              self.wavedesc_start + self.USER_TEXT_OFFSET + 4])[0]
        
        # COMM_TYPE (short, 2 bytes at offset 32)
        descriptor['COMM_TYPE'] = struct.unpack('<H',
            self.waveform_data[self.wavedesc_start + self.COMM_TYPE_OFFSET:
                              self.wavedesc_start + self.COMM_TYPE_OFFSET + 2])[0]
        
        # WAVE_ARRAY_1 (long, 4 bytes at offset 60)
        descriptor['WAVE_ARRAY_1'] = struct.unpack('<I',
            self.waveform_data[self.wavedesc_start + self.WAVE_ARRAY_1_OFFSET:
                              self.wavedesc_start + self.WAVE_ARRAY_1_OFFSET + 4])[0]
        
        # WAVE_ARRAY_COUNT (long, 4 bytes at offset 116)
        descriptor['WAVE_ARRAY_COUNT'] = struct.unpack('<I',
            self.waveform_data[self.wavedesc_start + self.WAVE_ARRAY_COUNT_OFFSET:
                              self.wavedesc_start + self.WAVE_ARRAY_COUNT_OFFSET + 4])[0]
        
        # VERTICAL_GAIN (float, 4 bytes at offset 156)
        descriptor['VERTICAL_GAIN'] = struct.unpack('<f',
            self.waveform_data[self.wavedesc_start + self.VERTICAL_GAIN_OFFSET:
                              self.wavedesc_start + self.VERTICAL_GAIN_OFFSET + 4])[0]
        
        # VERTICAL_OFFSET (float, 4 bytes at offset 160)
        descriptor['VERTICAL_OFFSET'] = struct.unpack('<f',
            self.waveform_data[self.wavedesc_start + self.VERTICAL_OFFSET_OFFSET:
                              self.wavedesc_start + self.VERTICAL_OFFSET_OFFSET + 4])[0]
        
        # HORIZ_INTERVAL (float, 4 bytes at offset 176)
        descriptor['HORIZ_INTERVAL'] = struct.unpack('<f',
            self.waveform_data[self.wavedesc_start + self.HORIZ_INTERVAL_OFFSET:
                              self.wavedesc_start + self.HORIZ_INTERVAL_OFFSET + 4])[0]
        
        # HORIZ_OFFSET (double, 8 bytes at offset 180)
        descriptor['HORIZ_OFFSET'] = struct.unpack('<d',
            self.waveform_data[self.wavedesc_start + self.HORIZ_OFFSET_OFFSET:
                              self.wavedesc_start + self.HORIZ_OFFSET_OFFSET + 8])[0]
        
        return descriptor

