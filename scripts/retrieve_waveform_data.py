#!/usr/bin/env python3
"""
Retrieve and Decode Oscilloscope Waveform Data

This script connects to the oscilloscope, retrieves Channel 1 waveform data
using the C1:WF? ALL command, and decodes the binary data according to the
waveform descriptor specification.
"""

import os
import sys
import struct
import logging
import time
import re
from pathlib import Path
from typing import List, Tuple, Optional

# Import numpy for array operations (optional but recommended)
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False

# Import scipy for filtering (optional but recommended)
try:
    from scipy import signal
    scipy_available = True
except ImportError:
    signal = None
    scipy_available = False

# Import matplotlib for plotting (optional)
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib_available = True
except ImportError:
    matplotlib = None
    plt = None
    matplotlib_available = False

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import OscilloscopeService
import importlib.util
osc_spec = importlib.util.spec_from_file_location(
    "oscilloscope_service",
    project_root / "host_gui" / "services" / "oscilloscope_service.py"
)
osc_module = importlib.util.module_from_spec(osc_spec)
osc_spec.loader.exec_module(osc_module)
OscilloscopeService = osc_module.OscilloscopeService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WaveformDecoder:
    """Decode waveform data from oscilloscope binary format."""
    
    # Byte offsets in WAVEDESC block (from specification)
    WAVEDESC_OFFSET = 0
    DESCRIPTOR_NAME_OFFSET = 0
    TEMPLATE_NAME_OFFSET = 16
    COMM_TYPE_OFFSET = 32
    COMM_ORDER_OFFSET = 34
    WAVE_DESCRIPTOR_LENGTH_OFFSET = 36
    USER_TEXT_LENGTH_OFFSET = 40
    RES_DESC1_OFFSET = 44
    TRIGTIME_ARRAY_OFFSET = 48
    RIS_TIME_ARRAY_OFFSET = 52
    RES_ARRAY1_OFFSET = 56
    WAVE_ARRAY_1_LENGTH_OFFSET = 60
    WAVE_ARRAY_2_LENGTH_OFFSET = 64
    RES_ARRAY2_OFFSET = 68
    RES_ARRAY3_OFFSET = 72
    INSTRUMENT_NAME_OFFSET = 76
    INSTRUMENT_NUMBER_OFFSET = 92
    TRACE_LABEL_OFFSET = 96
    RESERVED1_OFFSET = 112
    RESERVED2_OFFSET = 114
    WAVE_ARRAY_COUNT_OFFSET = 116
    PNTS_PER_SCREEN_OFFSET = 120
    FIRST_VALID_PNT_OFFSET = 124
    LAST_VALID_PNT_OFFSET = 128
    FIRST_POINT_OFFSET = 132
    SPARSING_FACTOR_OFFSET = 136
    SEGMENT_INDEX_OFFSET = 140
    SUBARRAY_COUNT_OFFSET = 144
    SWEEPS_PER_ACQ_OFFSET = 148
    POINTS_PER_PAIR_OFFSET = 152
    PAIR_OFFSET_OFFSET = 154
    VERTICAL_GAIN_OFFSET = 156
    VERTICAL_OFFSET_OFFSET = 160
    MAX_VALUE_OFFSET = 164
    MIN_VALUE_OFFSET = 168
    NOMINAL_BITS_OFFSET = 172
    NOM_SUBARRAY_COUNT_OFFSET = 174
    HORIZ_INTERVAL_OFFSET = 176
    HORIZ_OFFSET_OFFSET = 180
    PIXEL_OFFSET_OFFSET = 188
    VERTUNIT_OFFSET = 196
    HORUNIT_OFFSET = 244
    HORIZ_UNCERTAINTY_OFFSET = 292
    TRIGGER_TIME_OFFSET = 296
    ACQ_DURATION_OFFSET = 312
    RECORD_TYPE_OFFSET = 316
    PROCESSING_DONE_OFFSET = 318
    RESERVED5_OFFSET = 320
    RIS_SWEEPS_OFFSET = 322
    TIMEBASE_OFFSET = 324
    VERT_COUPLING_OFFSET = 326
    PROBE_ATT_OFFSET = 328
    FIXED_VERT_GAIN_OFFSET = 332
    BANDWIDTH_LIMIT_OFFSET = 334
    VERTICAL_VERNIER_OFFSET = 336
    ACQ_VERT_OFFSET_OFFSET = 340
    WAVE_SOURCE_OFFSET = 344
    
    # Data types
    COMM_TYPE_BYTE = 0
    COMM_TYPE_WORD = 1
    
    def __init__(self, waveform_data: bytes):
        """Initialize decoder with waveform binary data.
        
        Args:
            waveform_data: Raw binary data from C1:WF? ALL command
        """
        self.waveform_data = waveform_data
        self.wavedesc_start = 0
        
    def decode(self, vertical_gain: Optional[float] = None, vertical_offset: Optional[float] = None) -> Tuple[dict, List[float], List[float]]:
        """Decode waveform data.
        
        Args:
            vertical_gain: Optional vertical gain from C1:VDIV? command. If None, uses VERTICAL_GAIN from descriptor.
            vertical_offset: Optional vertical offset from C1:OFST? command. If None, uses VERTICAL_OFFSET from descriptor.
        
        Returns:
            Tuple of (descriptor_dict, time_values, voltage_values)
            - descriptor_dict: Dictionary with waveform metadata
            - time_values: List of time values in seconds
            - voltage_values: List of voltage/current values in units
        """
        if len(self.waveform_data) < 400:
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
        
        data_array_start = (self.wavedesc_start + 
                           wave_descriptor_length + 
                           user_text_length)
        
        # Extract data array
        wave_array_1_length = descriptor['WAVE_ARRAY_1']
        wave_array_count = descriptor['WAVE_ARRAY_COUNT']
        
        # The WAVE_ARRAY_1 length might be the total possible length, not actual transmitted
        # Use WAVE_ARRAY_COUNT and data format to calculate actual data length
        if comm_type == self.COMM_TYPE_BYTE:
            data_size = 1
        else:  # WORD
            data_size = 2
        
        # Calculate actual data length from count
        actual_data_length = wave_array_count * data_size
        
        # Use the smaller of the two (descriptor length vs calculated length)
        # or what's actually available
        available_data = len(self.waveform_data) - data_array_start
        data_length_to_use = min(wave_array_1_length, actual_data_length, available_data)
        
        if data_array_start > len(self.waveform_data):
            raise ValueError(f"Data array start position beyond waveform data: "
                           f"start={data_array_start}, total={len(self.waveform_data)}")
        
        if data_length_to_use <= 0:
            raise ValueError(f"Invalid data length: {data_length_to_use}")
        
        if data_length_to_use < actual_data_length:
            logger.warning(f"Using partial data: {data_length_to_use} bytes instead of "
                         f"expected {actual_data_length} bytes (from {wave_array_count} points)")
            # Adjust count to match available data
            wave_array_count = data_length_to_use // data_size
        
        data_array_bytes = self.waveform_data[data_array_start:data_array_start + data_length_to_use]
        
        # Unpack data points
        num_points = min(wave_array_count, len(data_array_bytes) // data_size)
        raw_data_points = struct.unpack(f'<{num_points}{data_format}', 
                                       data_array_bytes[:num_points * data_size])
        
        # Convert to floating point values using vertical gain and offset
        # Use provided values from C1:VDIV? and C1:OFST? if available, otherwise use descriptor values
        if vertical_gain is None:
        vertical_gain = descriptor['VERTICAL_GAIN']
            logger.info(f"Using VERTICAL_GAIN from descriptor: {vertical_gain}")
        else:
            logger.info(f"Using vertical gain from C1:VDIV?: {vertical_gain}")
        
        if vertical_offset is None:
        vertical_offset = descriptor['VERTICAL_OFFSET']
            logger.info(f"Using VERTICAL_OFFSET from descriptor: {vertical_offset}")
        else:
            logger.info(f"Using vertical offset from C1:OFST?: {vertical_offset}")
        
        # Optimized voltage conversion using NumPy vectorization
        if numpy_available:
            raw_data_array = np.array(raw_data_points, dtype=np.float32)
            voltage_values = ((vertical_gain * raw_data_array) / 25.0 - vertical_offset).tolist()
        else:
            # Fallback to Python loop if NumPy not available
        voltage_values = []
        for data_point in raw_data_points:
                # Formula: vertical_gain * data - vertical_offset
                # Note: If using VDIV (volts per division), the conversion may need adjustment
                # VDIV is typically the full-scale range divided by 8 divisions
                # For byte format (-128 to 127), full range is 256 counts
                # So: voltage = (VDIV * 8 / 256) * data_point - OFST = (VDIV / 32) * data_point - OFST
                # However, using VDIV directly as requested by user
                voltage = (vertical_gain * data_point)/25.0 - vertical_offset
            voltage_values.append(voltage)
        
        # Calculate time values - optimized using NumPy
        horiz_interval = descriptor['HORIZ_INTERVAL']
        horiz_offset = descriptor['HORIZ_OFFSET']
        
        if numpy_available:
            time_values = (np.arange(num_points, dtype=np.float64) * horiz_interval + horiz_offset).tolist()
        else:
            # Fallback to Python loop if NumPy not available
        time_values = []
        for i in range(num_points):
            time = (i * horiz_interval) + horiz_offset
            time_values.append(time)
        
        return descriptor, time_values, voltage_values
    
    def _parse_string(self, offset: int, length: int) -> str:
        """Parse null-terminated string from waveform data.
        
        Args:
            offset: Byte offset in waveform data
            length: Maximum length of string
            
        Returns:
            Decoded string
        """
        try:
            if offset + length > len(self.waveform_data):
                return ""
            string_bytes = self.waveform_data[offset:offset + length]
            null_pos = string_bytes.find(b'\x00')
            if null_pos >= 0:
                string_bytes = string_bytes[:null_pos]
            return string_bytes.decode('ascii', errors='ignore')
        except Exception:
            return ""
    
    def _parse_time_stamp(self, offset: int) -> dict:
        """Parse time_stamp structure (16 bytes) from waveform data.
        
        Args:
            offset: Byte offset in waveform data
            
        Returns:
            Dictionary with time components
        """
        try:
            if offset + 16 > len(self.waveform_data):
                return {'seconds': 0.0, 'minutes': 0, 'hours': 0, 'days': 0, 'months': 0, 'year': 0}
            
            # double seconds (8 bytes)
            seconds = struct.unpack('<d', self.waveform_data[offset:offset + 8])[0]
            # byte minutes (1 byte)
            minutes = struct.unpack('<B', self.waveform_data[offset + 8:offset + 9])[0]
            # byte hours (1 byte)
            hours = struct.unpack('<B', self.waveform_data[offset + 9:offset + 10])[0]
            # byte days (1 byte)
            days = struct.unpack('<B', self.waveform_data[offset + 10:offset + 11])[0]
            # byte months (1 byte)
            months = struct.unpack('<B', self.waveform_data[offset + 11:offset + 12])[0]
            # word year (2 bytes)
            year = struct.unpack('<H', self.waveform_data[offset + 12:offset + 14])[0]
            # word unused (2 bytes) - skip
            
            return {
                'seconds': seconds,
                'minutes': minutes,
                'hours': hours,
                'days': days,
                'months': months,
                'year': year
            }
        except Exception:
            return {'seconds': 0.0, 'minutes': 0, 'hours': 0, 'days': 0, 'months': 0, 'year': 0}
    
    def _parse_unit_definition(self, offset: int) -> str:
        """Parse unit_definition (48 bytes) from waveform data.
        
        Args:
            offset: Byte offset in waveform data
            
        Returns:
            Unit name string
        """
        return self._parse_string(offset, 48)
    
    def _parse_wavedesc(self) -> dict:
        """Parse WAVEDESC block from waveform data.
        
        Returns:
            Dictionary with waveform descriptor fields
        """
        # Verify descriptor name
        descriptor_name = self._parse_string(self.DESCRIPTOR_NAME_OFFSET, 8)
        if not descriptor_name.startswith('WAVEDESC'):
            logger.warning(f"Descriptor name doesn't start with WAVEDESC: {descriptor_name}")
        descriptor = {'DESCRIPTOR_NAME': descriptor_name}
        
        # TEMPLATE_NAME (string, 16 bytes at offset 16)
        descriptor['TEMPLATE_NAME'] = self._parse_string(self.TEMPLATE_NAME_OFFSET, 16)
        
        # COMM_TYPE (enum, 2 bytes at offset 32)
        descriptor['COMM_TYPE'] = struct.unpack('<H', 
            self.waveform_data[self.COMM_TYPE_OFFSET:self.COMM_TYPE_OFFSET + 2])[0]
        
        # COMM_ORDER (enum, 2 bytes at offset 34)
        descriptor['COMM_ORDER'] = struct.unpack('<H', 
            self.waveform_data[self.COMM_ORDER_OFFSET:self.COMM_ORDER_OFFSET + 2])[0]
        
        # Block lengths
        # WAVE_DESCRIPTOR length (long, 4 bytes at offset 36)
        descriptor['WAVE_DESCRIPTOR'] = struct.unpack('<I', 
            self.waveform_data[self.WAVE_DESCRIPTOR_LENGTH_OFFSET:
                              self.WAVE_DESCRIPTOR_LENGTH_OFFSET + 4])[0]
        
        # USER_TEXT length (long, 4 bytes at offset 40)
        descriptor['USER_TEXT'] = struct.unpack('<I',
            self.waveform_data[self.USER_TEXT_LENGTH_OFFSET:
                              self.USER_TEXT_LENGTH_OFFSET + 4])[0]
        
        # RES_DESC1 (long, 4 bytes at offset 44)
        descriptor['RES_DESC1'] = struct.unpack('<I',
            self.waveform_data[self.RES_DESC1_OFFSET:self.RES_DESC1_OFFSET + 4])[0]
        
        # TRIGTIME_ARRAY (long, 4 bytes at offset 48)
        descriptor['TRIGTIME_ARRAY'] = struct.unpack('<I',
            self.waveform_data[self.TRIGTIME_ARRAY_OFFSET:self.TRIGTIME_ARRAY_OFFSET + 4])[0]
        
        # RIS_TIME_ARRAY (long, 4 bytes at offset 52)
        descriptor['RIS_TIME_ARRAY'] = struct.unpack('<I',
            self.waveform_data[self.RIS_TIME_ARRAY_OFFSET:self.RIS_TIME_ARRAY_OFFSET + 4])[0]
        
        # RES_ARRAY1 (long, 4 bytes at offset 56)
        descriptor['RES_ARRAY1'] = struct.unpack('<I',
            self.waveform_data[self.RES_ARRAY1_OFFSET:self.RES_ARRAY1_OFFSET + 4])[0]
        
        # WAVE_ARRAY_1 length (long, 4 bytes at offset 60)
        descriptor['WAVE_ARRAY_1'] = struct.unpack('<I',
            self.waveform_data[self.WAVE_ARRAY_1_LENGTH_OFFSET:
                              self.WAVE_ARRAY_1_LENGTH_OFFSET + 4])[0]
        
        # WAVE_ARRAY_2 length (long, 4 bytes at offset 64)
        descriptor['WAVE_ARRAY_2'] = struct.unpack('<I',
            self.waveform_data[self.WAVE_ARRAY_2_LENGTH_OFFSET:
                              self.WAVE_ARRAY_2_LENGTH_OFFSET + 4])[0]
        
        # RES_ARRAY2 (long, 4 bytes at offset 68)
        descriptor['RES_ARRAY2'] = struct.unpack('<I',
            self.waveform_data[self.RES_ARRAY2_OFFSET:self.RES_ARRAY2_OFFSET + 4])[0]
        
        # RES_ARRAY3 (long, 4 bytes at offset 72)
        descriptor['RES_ARRAY3'] = struct.unpack('<I',
            self.waveform_data[self.RES_ARRAY3_OFFSET:self.RES_ARRAY3_OFFSET + 4])[0]
        
        # Instrument identification
        # INSTRUMENT_NAME (string, 16 bytes at offset 76)
        descriptor['INSTRUMENT_NAME'] = self._parse_string(self.INSTRUMENT_NAME_OFFSET, 16)
        
        # INSTRUMENT_NUMBER (long, 4 bytes at offset 92)
        descriptor['INSTRUMENT_NUMBER'] = struct.unpack('<I',
            self.waveform_data[self.INSTRUMENT_NUMBER_OFFSET:
                              self.INSTRUMENT_NUMBER_OFFSET + 4])[0]
        
        # TRACE_LABEL (string, 16 bytes at offset 96)
        descriptor['TRACE_LABEL'] = self._parse_string(self.TRACE_LABEL_OFFSET, 16)
        
        # RESERVED1 (word, 2 bytes at offset 112)
        descriptor['RESERVED1'] = struct.unpack('<H',
            self.waveform_data[self.RESERVED1_OFFSET:self.RESERVED1_OFFSET + 2])[0]
        
        # RESERVED2 (word, 2 bytes at offset 114)
        descriptor['RESERVED2'] = struct.unpack('<H',
            self.waveform_data[self.RESERVED2_OFFSET:self.RESERVED2_OFFSET + 2])[0]
        
        # Waveform description
        # WAVE_ARRAY_COUNT (long, 4 bytes at offset 116)
        descriptor['WAVE_ARRAY_COUNT'] = struct.unpack('<I',
            self.waveform_data[self.WAVE_ARRAY_COUNT_OFFSET:
                              self.WAVE_ARRAY_COUNT_OFFSET + 4])[0]
        
        # PNTS_PER_SCREEN (long, 4 bytes at offset 120)
        descriptor['PNTS_PER_SCREEN'] = struct.unpack('<I',
            self.waveform_data[self.PNTS_PER_SCREEN_OFFSET:
                              self.PNTS_PER_SCREEN_OFFSET + 4])[0]
        
        # FIRST_VALID_PNT (long, 4 bytes at offset 124)
        descriptor['FIRST_VALID_PNT'] = struct.unpack('<I',
            self.waveform_data[self.FIRST_VALID_PNT_OFFSET:
                              self.FIRST_VALID_PNT_OFFSET + 4])[0]
        
        # LAST_VALID_PNT (long, 4 bytes at offset 128)
        descriptor['LAST_VALID_PNT'] = struct.unpack('<I',
            self.waveform_data[self.LAST_VALID_PNT_OFFSET:
                              self.LAST_VALID_PNT_OFFSET + 4])[0]
        
        # FIRST_POINT (long, 4 bytes at offset 132)
        descriptor['FIRST_POINT'] = struct.unpack('<I',
            self.waveform_data[self.FIRST_POINT_OFFSET:
                              self.FIRST_POINT_OFFSET + 4])[0]
        
        # SPARSING_FACTOR (long, 4 bytes at offset 136)
        descriptor['SPARSING_FACTOR'] = struct.unpack('<I',
            self.waveform_data[self.SPARSING_FACTOR_OFFSET:
                              self.SPARSING_FACTOR_OFFSET + 4])[0]
        
        # SEGMENT_INDEX (long, 4 bytes at offset 140)
        descriptor['SEGMENT_INDEX'] = struct.unpack('<I',
            self.waveform_data[self.SEGMENT_INDEX_OFFSET:
                              self.SEGMENT_INDEX_OFFSET + 4])[0]
        
        # SUBARRAY_COUNT (long, 4 bytes at offset 144)
        descriptor['SUBARRAY_COUNT'] = struct.unpack('<I',
            self.waveform_data[self.SUBARRAY_COUNT_OFFSET:
                              self.SUBARRAY_COUNT_OFFSET + 4])[0]
        
        # SWEEPS_PER_ACQ (long, 4 bytes at offset 148)
        descriptor['SWEEPS_PER_ACQ'] = struct.unpack('<I',
            self.waveform_data[self.SWEEPS_PER_ACQ_OFFSET:
                              self.SWEEPS_PER_ACQ_OFFSET + 4])[0]
        
        # POINTS_PER_PAIR (word, 2 bytes at offset 152)
        descriptor['POINTS_PER_PAIR'] = struct.unpack('<H',
            self.waveform_data[self.POINTS_PER_PAIR_OFFSET:
                              self.POINTS_PER_PAIR_OFFSET + 2])[0]
        
        # PAIR_OFFSET (word, 2 bytes at offset 154)
        descriptor['PAIR_OFFSET'] = struct.unpack('<H',
            self.waveform_data[self.PAIR_OFFSET_OFFSET:
                              self.PAIR_OFFSET_OFFSET + 2])[0]
        
        # Vertical parameters
        # VERTICAL_GAIN (float, 4 bytes at offset 156)
        descriptor['VERTICAL_GAIN'] = struct.unpack('<f',
            self.waveform_data[self.VERTICAL_GAIN_OFFSET:
                              self.VERTICAL_GAIN_OFFSET + 4])[0]
        
        # VERTICAL_OFFSET (float, 4 bytes at offset 160)
        descriptor['VERTICAL_OFFSET'] = struct.unpack('<f',
            self.waveform_data[self.VERTICAL_OFFSET_OFFSET:
                              self.VERTICAL_OFFSET_OFFSET + 4])[0]
        
        # MAX_VALUE (float, 4 bytes at offset 164)
        descriptor['MAX_VALUE'] = struct.unpack('<f',
            self.waveform_data[self.MAX_VALUE_OFFSET:
                              self.MAX_VALUE_OFFSET + 4])[0]
        
        # MIN_VALUE (float, 4 bytes at offset 168)
        descriptor['MIN_VALUE'] = struct.unpack('<f',
            self.waveform_data[self.MIN_VALUE_OFFSET:
                              self.MIN_VALUE_OFFSET + 4])[0]
        
        # NOMINAL_BITS (word, 2 bytes at offset 172)
        descriptor['NOMINAL_BITS'] = struct.unpack('<H',
            self.waveform_data[self.NOMINAL_BITS_OFFSET:
                              self.NOMINAL_BITS_OFFSET + 2])[0]
        
        # NOM_SUBARRAY_COUNT (word, 2 bytes at offset 174)
        descriptor['NOM_SUBARRAY_COUNT'] = struct.unpack('<H',
            self.waveform_data[self.NOM_SUBARRAY_COUNT_OFFSET:
                              self.NOM_SUBARRAY_COUNT_OFFSET + 2])[0]
        
        # Horizontal parameters
        # HORIZ_INTERVAL (float, 4 bytes at offset 176)
        descriptor['HORIZ_INTERVAL'] = struct.unpack('<f',
            self.waveform_data[self.HORIZ_INTERVAL_OFFSET:
                              self.HORIZ_INTERVAL_OFFSET + 4])[0]
        
        # HORIZ_OFFSET (double, 8 bytes at offset 180)
        descriptor['HORIZ_OFFSET'] = struct.unpack('<d',
            self.waveform_data[self.HORIZ_OFFSET_OFFSET:
                              self.HORIZ_OFFSET_OFFSET + 8])[0]
        
        # PIXEL_OFFSET (double, 8 bytes at offset 188)
        descriptor['PIXEL_OFFSET'] = struct.unpack('<d',
            self.waveform_data[self.PIXEL_OFFSET_OFFSET:
                              self.PIXEL_OFFSET_OFFSET + 8])[0]
        
        # VERTUNIT (unit_definition, 48 bytes at offset 196)
        descriptor['VERTUNIT'] = self._parse_unit_definition(self.VERTUNIT_OFFSET)
        
        # HORUNIT (unit_definition, 48 bytes at offset 244)
        descriptor['HORUNIT'] = self._parse_unit_definition(self.HORUNIT_OFFSET)
        
        # HORIZ_UNCERTAINTY (float, 4 bytes at offset 292)
        descriptor['HORIZ_UNCERTAINTY'] = struct.unpack('<f',
            self.waveform_data[self.HORIZ_UNCERTAINTY_OFFSET:
                              self.HORIZ_UNCERTAINTY_OFFSET + 4])[0]
        
        # TRIGGER_TIME (time_stamp, 16 bytes at offset 296)
        descriptor['TRIGGER_TIME'] = self._parse_time_stamp(self.TRIGGER_TIME_OFFSET)
        
        # ACQ_DURATION (float, 4 bytes at offset 312)
        descriptor['ACQ_DURATION'] = struct.unpack('<f',
            self.waveform_data[self.ACQ_DURATION_OFFSET:
                              self.ACQ_DURATION_OFFSET + 4])[0]
        
        # RECORD_TYPE (enum, 2 bytes at offset 316)
        descriptor['RECORD_TYPE'] = struct.unpack('<H',
            self.waveform_data[self.RECORD_TYPE_OFFSET:
                              self.RECORD_TYPE_OFFSET + 2])[0]
        
        # PROCESSING_DONE (enum, 2 bytes at offset 318)
        descriptor['PROCESSING_DONE'] = struct.unpack('<H',
            self.waveform_data[self.PROCESSING_DONE_OFFSET:
                              self.PROCESSING_DONE_OFFSET + 2])[0]
        
        # RESERVED5 (word, 2 bytes at offset 320)
        descriptor['RESERVED5'] = struct.unpack('<H',
            self.waveform_data[self.RESERVED5_OFFSET:
                              self.RESERVED5_OFFSET + 2])[0]
        
        # RIS_SWEEPS (word, 2 bytes at offset 322)
        descriptor['RIS_SWEEPS'] = struct.unpack('<H',
            self.waveform_data[self.RIS_SWEEPS_OFFSET:
                              self.RIS_SWEEPS_OFFSET + 2])[0]
        
        # Acquisition conditions
        # TIMEBASE (enum, 2 bytes at offset 324)
        descriptor['TIMEBASE'] = struct.unpack('<H',
            self.waveform_data[self.TIMEBASE_OFFSET:
                              self.TIMEBASE_OFFSET + 2])[0]
        
        # VERT_COUPLING (enum, 2 bytes at offset 326)
        descriptor['VERT_COUPLING'] = struct.unpack('<H',
            self.waveform_data[self.VERT_COUPLING_OFFSET:
                              self.VERT_COUPLING_OFFSET + 2])[0]
        
        # PROBE_ATT (float, 4 bytes at offset 328)
        descriptor['PROBE_ATT'] = struct.unpack('<f',
            self.waveform_data[self.PROBE_ATT_OFFSET:
                              self.PROBE_ATT_OFFSET + 4])[0]
        
        # FIXED_VERT_GAIN (enum, 2 bytes at offset 332)
        descriptor['FIXED_VERT_GAIN'] = struct.unpack('<H',
            self.waveform_data[self.FIXED_VERT_GAIN_OFFSET:
                              self.FIXED_VERT_GAIN_OFFSET + 2])[0]
        
        # BANDWIDTH_LIMIT (enum, 2 bytes at offset 334)
        descriptor['BANDWIDTH_LIMIT'] = struct.unpack('<H',
            self.waveform_data[self.BANDWIDTH_LIMIT_OFFSET:
                              self.BANDWIDTH_LIMIT_OFFSET + 2])[0]
        
        # VERTICAL_VERNIER (float, 4 bytes at offset 336)
        descriptor['VERTICAL_VERNIER'] = struct.unpack('<f',
            self.waveform_data[self.VERTICAL_VERNIER_OFFSET:
                              self.VERTICAL_VERNIER_OFFSET + 4])[0]
        
        # ACQ_VERT_OFFSET (float, 4 bytes at offset 340)
        descriptor['ACQ_VERT_OFFSET'] = struct.unpack('<f',
            self.waveform_data[self.ACQ_VERT_OFFSET_OFFSET:
                              self.ACQ_VERT_OFFSET_OFFSET + 4])[0]
        
        # WAVE_SOURCE (enum, 2 bytes at offset 344)
        descriptor['WAVE_SOURCE'] = struct.unpack('<H',
            self.waveform_data[self.WAVE_SOURCE_OFFSET:
                              self.WAVE_SOURCE_OFFSET + 2])[0]
        
        return descriptor


def query_vertical_gain(oscilloscope_service: OscilloscopeService) -> Optional[float]:
    """Query vertical gain (volts per division) from oscilloscope.
    
    Args:
        oscilloscope_service: Connected OscilloscopeService instance
        
    Returns:
        Vertical gain value in volts per division, or None if query fails
    """
    try:
        resp = oscilloscope_service.send_command("C1:VDIV?")
        if resp is None:
            logger.warning("C1:VDIV? - No response")
            return None
        
        # Parse vertical scale value (handles exponential format like 1.5e-2, 5.0e+1)
        vdiv_match = re.search(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp, re.IGNORECASE)
        if vdiv_match:
            try:
                return float(vdiv_match.group(1))
            except ValueError:
                logger.warning(f"C1:VDIV? - Could not convert to float: {vdiv_match.group(1)}")
                return None
        else:
            # Fallback: try to find any number (including exponential) in the response
            numbers = re.findall(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp)
            if numbers:
                try:
                    return float(numbers[-1])
                except ValueError:
                    logger.warning(f"C1:VDIV? - Could not convert to float: {numbers[-1]}")
                    return None
            else:
                logger.warning(f"C1:VDIV? - Could not parse: {resp.strip()}")
                return None
    except Exception as e:
        logger.error(f"Error querying C1:VDIV?: {e}", exc_info=True)
        return None


def query_vertical_offset(oscilloscope_service: OscilloscopeService) -> Optional[float]:
    """Query vertical offset from oscilloscope.
    
    Args:
        oscilloscope_service: Connected OscilloscopeService instance
        
    Returns:
        Vertical offset value in volts, or None if query fails
    """
    try:
        resp = oscilloscope_service.send_command("C1:OFST?")
        if resp is None:
            logger.warning("C1:OFST? - No response")
            return None
        
        # Parse offset value (handles exponential format)
        ofst_match = re.search(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp, re.IGNORECASE)
        if ofst_match:
            try:
                return float(ofst_match.group(1))
            except ValueError:
                logger.warning(f"C1:OFST? - Could not convert to float: {ofst_match.group(1)}")
                return None
        else:
            # Fallback: try to find any number (including exponential) in the response
            numbers = re.findall(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp)
            if numbers:
                try:
                    return float(numbers[-1])
                except ValueError:
                    logger.warning(f"C1:OFST? - Could not convert to float: {numbers[-1]}")
                    return None
            else:
                logger.warning(f"C1:OFST? - Could not parse: {resp.strip()}")
                return None
    except Exception as e:
        logger.error(f"Error querying C1:OFST?: {e}", exc_info=True)
        return None


def analyze_steady_state(
    time_values: List[float],
    voltage_values: List[float],
    window_size: Optional[int] = None,
    variance_threshold_percent: float = 1.0,
    skip_initial_percent: float = 10.0
) -> Tuple[int, int, float, float]:
    """Analyze waveform to find steady state region and compute average.
    
    This function uses a rolling window approach to detect regions with low variance,
    which typically indicates steady state behavior.
    
    Args:
        time_values: List of time values in seconds
        voltage_values: List of voltage values
        window_size: Size of rolling window for variance calculation. If None, uses 1% of data points.
        variance_threshold_percent: Maximum coefficient of variation (std/mean * 100) for steady state (default 1.0%)
        skip_initial_percent: Percentage of initial data to skip when looking for steady state (default 10%)
        
    Returns:
        Tuple of (start_index, end_index, average_voltage, std_deviation)
        - start_index: Index where steady state begins
        - end_index: Index where steady state ends (exclusive)
        - average_voltage: Average voltage in steady state region
        - std_deviation: Standard deviation in steady state region
    """
    if not voltage_values or len(voltage_values) < 10:
        raise ValueError("Insufficient data points for steady state analysis")
    
    if numpy_available:
        voltages = np.array(voltage_values)
        times = np.array(time_values)
    else:
        voltages = voltage_values
        times = time_values
    
    num_points = len(voltage_values)
    
    # Determine window size (1% of data points, minimum 10, maximum 2000)
    # Use larger window for better statistical significance
    if window_size is None:
        window_size = max(10, min(2000, num_points // 100))
    
    # Skip initial transient period
    skip_points = int(num_points * skip_initial_percent / 100.0)
    search_start = max(skip_points, window_size)
    search_end = num_points - window_size
    
    if search_start >= search_end:
        # Not enough data after skipping initial portion
        search_start = window_size
        search_end = num_points - window_size
    
    if search_start >= search_end:
        # Still not enough data, use all available
        search_start = 0
        search_end = num_points
    
    logger.info(f"Analyzing steady state: window_size={window_size}, "
               f"search_range=[{search_start}:{search_end}], "
               f"variance_threshold={variance_threshold_percent}%")
    
    # Find region with lowest variance
    best_start = search_start
    best_variance = float('inf')
    best_mean = 0.0
    
    if numpy_available:
        # Use numpy for efficient rolling window calculations
        for start_idx in range(search_start, search_end):
            window_data = voltages[start_idx:start_idx + window_size]
            window_mean = np.mean(window_data)
            window_std = np.std(window_data)
            
            # Use coefficient of variation (CV) = std/mean * 100
            if abs(window_mean) > 1e-10:  # Avoid division by zero
                cv = abs(window_std / window_mean) * 100
            else:
                cv = window_std * 100  # Use absolute std if mean is near zero
            
            # Prefer regions with low CV that meet threshold
            if cv < variance_threshold_percent and window_std < best_variance:
                best_variance = window_std
                best_start = start_idx
                best_mean = window_mean
    else:
        # Manual calculation without numpy
        for start_idx in range(search_start, search_end):
            window_data = voltages[start_idx:start_idx + window_size]
            window_mean = sum(window_data) / len(window_data)
            window_variance = sum((x - window_mean) ** 2 for x in window_data) / len(window_data)
            window_std = window_variance ** 0.5
            
            # Use coefficient of variation
            if abs(window_mean) > 1e-10:
                cv = abs(window_std / window_mean) * 100
            else:
                cv = window_std * 100
            
            if cv < variance_threshold_percent and window_std < best_variance:
                best_variance = window_std
                best_start = start_idx
                best_mean = window_mean
    
    # If no region met the threshold, use the region with lowest variance
    if best_variance == float('inf'):
        logger.warning("No region met variance threshold, using region with lowest variance")
        if numpy_available:
            for start_idx in range(search_start, search_end):
                window_data = voltages[start_idx:start_idx + window_size]
                window_std = np.std(window_data)
                if window_std < best_variance:
                    best_variance = window_std
                    best_start = start_idx
                    best_mean = np.mean(window_data)
        else:
            for start_idx in range(search_start, search_end):
                window_data = voltages[start_idx:start_idx + window_size]
                window_mean = sum(window_data) / len(window_data)
                window_variance = sum((x - window_mean) ** 2 for x in window_data) / len(window_data)
                window_std = window_variance ** 0.5
                if window_std < best_variance:
                    best_variance = window_std
                    best_start = start_idx
                    best_mean = window_mean
    
    # Extend steady state region forward while variance remains low
    steady_start = best_start
    steady_end = best_start + window_size
    
    # Get reference mean for trend detection
    reference_mean = best_mean
    
    # Extend backward - but check for trends to avoid ramp-up
    # Optimized: use faster first-order difference instead of polyfit
    while steady_start > search_start:  # Don't extend before search_start
        if steady_start + window_size <= len(voltages):
            test_data = voltages[steady_start - 1:steady_start + window_size - 1]
            if numpy_available:
                test_std = np.std(test_data)
                test_mean = np.mean(test_data)
                # Optimized: use first-order difference instead of polyfit (much faster)
                if len(test_data) > 10:
                    # Calculate average rate of change using first-order difference
                    diff = np.diff(test_data)
                    avg_diff = np.mean(np.abs(diff))
                    # Normalize by mean to get relative change rate
                    if abs(test_mean) > 1e-10:
                        relative_slope = abs(avg_diff / test_mean) * 100  # Percentage change per sample
                    else:
                        relative_slope = abs(avg_diff) * 100
                else:
                    relative_slope = 0
            else:
                test_mean = sum(test_data) / len(test_data)
                test_variance = sum((x - test_mean) ** 2 for x in test_data) / len(test_data)
                test_std = test_variance ** 0.5
                # Simple trend detection: compare first and second half
                if len(test_data) > 10:
                    mid = len(test_data) // 2
                    first_half_mean = sum(test_data[:mid]) / mid
                    second_half_mean = sum(test_data[mid:]) / (len(test_data) - mid)
                    if abs(test_mean) > 1e-10:
                        relative_slope = abs((second_half_mean - first_half_mean) / test_mean) * 100
                    else:
                        relative_slope = abs(second_half_mean - first_half_mean) * 100
                else:
                    relative_slope = 0
            
            if abs(test_mean) > 1e-10:
                test_cv = abs(test_std / test_mean) * 100
            else:
                test_cv = test_std * 100
            
            # Check: variance must be low AND no significant trend AND mean is close to reference
            mean_diff_percent = abs((test_mean - reference_mean) / reference_mean) * 100 if abs(reference_mean) > 1e-10 else abs(test_mean - reference_mean) * 100
            
            # More strict: require low CV, low trend, and mean close to reference
            if (test_cv <= variance_threshold_percent * 1.5 and 
                relative_slope < 0.5 and  # Less than 0.5% change per sample
                mean_diff_percent < 2.0):  # Mean within 2% of reference
                steady_start -= 1
            else:
                break
        else:
            break
    
    # Extend forward - also check for trends
    # Optimized: use faster first-order difference instead of polyfit
    while steady_end < len(voltages):
        if steady_end - window_size >= 0:
            test_data = voltages[steady_end - window_size:steady_end]
            if numpy_available:
                test_std = np.std(test_data)
                test_mean = np.mean(test_data)
                # Optimized: use first-order difference instead of polyfit (much faster)
                if len(test_data) > 10:
                    # Calculate average rate of change using first-order difference
                    diff = np.diff(test_data)
                    avg_diff = np.mean(np.abs(diff))
                    if abs(test_mean) > 1e-10:
                        relative_slope = abs(avg_diff / test_mean) * 100
                    else:
                        relative_slope = abs(avg_diff) * 100
                else:
                    relative_slope = 0
            else:
                test_mean = sum(test_data) / len(test_data)
                test_variance = sum((x - test_mean) ** 2 for x in test_data) / len(test_data)
                test_std = test_variance ** 0.5
                if len(test_data) > 10:
                    mid = len(test_data) // 2
                    first_half_mean = sum(test_data[:mid]) / mid
                    second_half_mean = sum(test_data[mid:]) / (len(test_data) - mid)
                    if abs(test_mean) > 1e-10:
                        relative_slope = abs((second_half_mean - first_half_mean) / test_mean) * 100
                    else:
                        relative_slope = abs(second_half_mean - first_half_mean) * 100
                else:
                    relative_slope = 0
            
            if abs(test_mean) > 1e-10:
                test_cv = abs(test_std / test_mean) * 100
            else:
                test_cv = test_std * 100
            
            mean_diff_percent = abs((test_mean - reference_mean) / reference_mean) * 100 if abs(reference_mean) > 1e-10 else abs(test_mean - reference_mean) * 100
            
            # Check: variance must be low AND no significant trend AND mean is close to reference
            if (test_cv <= variance_threshold_percent * 1.5 and 
                relative_slope < 0.5 and  # Less than 0.5% change per sample
                mean_diff_percent < 2.0):  # Mean within 2% of reference
                steady_end += 1
            else:
                break
        else:
            break
    
    # Calculate final statistics for steady state region
    steady_state_data = voltages[steady_start:steady_end]
    if numpy_available:
        steady_state_mean = np.mean(steady_state_data)
        steady_state_std = np.std(steady_state_data)
    else:
        steady_state_mean = sum(steady_state_data) / len(steady_state_data)
        steady_state_variance = sum((x - steady_state_mean) ** 2 for x in steady_state_data) / len(steady_state_data)
        steady_state_std = steady_state_variance ** 0.5
    
    return steady_start, steady_end, float(steady_state_mean), float(steady_state_std)


def apply_lowpass_filter(
    time_values: List[float],
    voltage_values: List[float],
    cutoff_freq: float = 5000.0,
    filter_order: int = 4
) -> List[float]:
    """Apply a low-pass Butterworth filter to the voltage waveform.
    
    Args:
        time_values: List of time values in seconds
        voltage_values: List of voltage values to filter
        cutoff_freq: Cutoff frequency in Hz (default 10kHz)
        filter_order: Filter order (default 4)
        
    Returns:
        Filtered voltage values
    """
    if not voltage_values or len(voltage_values) < 10:
        raise ValueError("Insufficient data points for filtering")
    
    if not numpy_available:
        logger.warning("NumPy not available - cannot apply digital filter")
        logger.warning("Returning unfiltered data. Install numpy for filtering: pip install numpy")
        return voltage_values
    
    if not scipy_available:
        logger.warning("SciPy not available - using simple moving average filter")
        logger.warning("Install scipy for proper Butterworth filter: pip install scipy")
        # Fallback to simple moving average
        return _apply_moving_average_filter(voltage_values, window_size=10)
    
    # Convert to numpy arrays
    voltages = np.array(voltage_values)
    times = np.array(time_values)
    
    # Calculate sampling frequency
    if len(time_values) < 2:
        raise ValueError("Need at least 2 time points to calculate sampling frequency")
    
    dt = time_values[1] - time_values[0]
    if dt <= 0:
        # Try to calculate from average
        dt = (time_values[-1] - time_values[0]) / (len(time_values) - 1)
        if dt <= 0:
            raise ValueError("Invalid time values for filtering")
    
    sampling_freq = 1.0 / dt
    
    # Check if cutoff frequency is valid (must be less than Nyquist frequency)
    nyquist_freq = sampling_freq / 2.0
    if cutoff_freq >= nyquist_freq:
        logger.warning(f"Cutoff frequency {cutoff_freq} Hz is >= Nyquist frequency {nyquist_freq:.2f} Hz")
        logger.warning(f"Reducing cutoff to {nyquist_freq * 0.9:.2f} Hz")
        cutoff_freq = nyquist_freq * 0.9
    
    # Normalize cutoff frequency (0 to 1, where 1 is Nyquist)
    normalized_cutoff = cutoff_freq / nyquist_freq
    
    logger.info(f"Applying low-pass filter: cutoff={cutoff_freq:.2f} Hz, "
               f"order={filter_order}, sampling_freq={sampling_freq:.2f} Hz")
    
    try:
        # Design Butterworth low-pass filter
        b, a = signal.butter(filter_order, normalized_cutoff, btype='low', analog=False)
        
        # Apply filter
        filtered_voltages = signal.filtfilt(b, a, voltages)
        
        logger.info("Filter applied successfully using filtfilt (zero-phase filtering)")
        
        return filtered_voltages.tolist()
        
    except Exception as e:
        logger.error(f"Error applying filter: {e}", exc_info=True)
        logger.warning("Returning unfiltered data")
        return voltage_values


def _apply_moving_average_filter(voltage_values: List[float], window_size: int = 10) -> List[float]:
    """Apply a simple moving average filter (fallback when scipy is not available).
    
    Args:
        voltage_values: List of voltage values
        window_size: Size of moving average window
        
    Returns:
        Filtered voltage values
    """
    if len(voltage_values) < window_size:
        return voltage_values
    
    # Optimized: use NumPy convolution if available (much faster)
    if numpy_available:
        window = np.ones(window_size, dtype=np.float32) / window_size
        filtered = np.convolve(voltage_values, window, mode='same')
        return filtered.tolist()
    
    # Fallback to Python loop if NumPy not available
    filtered = []
    half_window = window_size // 2
    
    for i in range(len(voltage_values)):
        start_idx = max(0, i - half_window)
        end_idx = min(len(voltage_values), i + half_window + 1)
        window_data = voltage_values[start_idx:end_idx]
        filtered.append(sum(window_data) / len(window_data))
    
    return filtered


def retrieve_waveform(oscilloscope_service: OscilloscopeService) -> Optional[bytes]:
    """Retrieve waveform data from Channel 1.
    
    Args:
        oscilloscope_service: Connected OscilloscopeService instance
        
    Returns:
        Binary waveform data or None if retrieval fails
    """
    if not oscilloscope_service.is_connected():
        logger.error("Oscilloscope not connected")
        return None
    
    try:
        logger.info("Retrieving Channel 1 waveform data (C1:WF? ALL)...")
        
        oscilloscope = oscilloscope_service.oscilloscope
        
        # Set timeout for large data transfer
        original_timeout = oscilloscope.timeout
        oscilloscope.timeout = 10000  # 10 seconds for large waveform data
        
        try:
            # Send query command - waveform data is binary
            oscilloscope.write("C1:WF? ALL")
            
            # Read binary data - may need to read in chunks for large waveforms
            # First, try to read the header to determine total length
            raw_data = b''
            chunk_size = 4096
            max_reads = 1000  # Safety limit
            
            # Read first chunk to see format
            try:
                first_chunk = oscilloscope.read_raw()
                raw_data += first_chunk
                logger.info(f"Read first chunk: {len(first_chunk)} bytes")
            except Exception as e:
                logger.error(f"Failed to read first chunk: {e}")
                return None
            
            # Check if it's SCPI binary block format
            if len(raw_data) >= 2 and raw_data[0] == ord('#'):
                # Parse length from SCPI header
                num_digits = int(chr(raw_data[1]))
                if 1 <= num_digits <= 9:
                    length_str = raw_data[2:2+num_digits].decode('ascii')
                    total_length = int(length_str)
                    header_size = 2 + num_digits
                    logger.info(f"SCPI binary block format: total length={total_length}, header={header_size}")
                    
                    # Read remaining data
                    remaining = total_length + header_size - len(raw_data) + 1  # +1 for newline
                    if remaining > 0:
                        logger.info(f"Reading remaining {remaining} bytes...")
                        read_count = 0
                        while len(raw_data) < total_length + header_size + 1 and read_count < max_reads:
                            try:
                                chunk = oscilloscope.read_raw()
                                if not chunk:
                                    break
                                raw_data += chunk
                                read_count += 1
                                if read_count % 10 == 0:
                                    logger.debug(f"Read {len(raw_data)} bytes so far...")
                            except Exception as e:
                                logger.warning(f"Error reading chunk: {e}")
                                break
            else:
                # Direct binary - read until we get WAVEDESC and then parse to determine length
                # Or read in chunks until timeout/end
                logger.info("Direct binary format, reading in chunks...")
                read_count = 0
                while read_count < max_reads:
                    try:
                        chunk = oscilloscope.read_raw()
                        if not chunk:
                            break
                        raw_data += chunk
                        read_count += 1
                        # Check if we have enough to parse WAVEDESC
                        if len(raw_data) >= 400:
                            wavedesc_pos = raw_data.find(b'WAVEDESC')
                            if wavedesc_pos >= 0:
                                # Try to parse WAVE_ARRAY_1 length to know how much more to read
                                try:
                                    wave_array_1_offset = wavedesc_pos + 60
                                    if len(raw_data) >= wave_array_1_offset + 4:
                                        wave_array_1_length = struct.unpack('<I', 
                                            raw_data[wave_array_1_offset:wave_array_1_offset + 4])[0]
                                        wave_descriptor_length = struct.unpack('<I',
                                            raw_data[wavedesc_pos + 36:wavedesc_pos + 40])[0]
                                        user_text_length = struct.unpack('<I',
                                            raw_data[wavedesc_pos + 40:wavedesc_pos + 44])[0]
                                        
                                        expected_total = (wavedesc_pos + wave_descriptor_length + 
                                                         user_text_length + wave_array_1_length)
                                        if len(raw_data) >= expected_total:
                                            logger.info(f"Read complete waveform: {len(raw_data)} bytes")
                                            break
                                        else:
                                            logger.debug(f"Need {expected_total - len(raw_data)} more bytes...")
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"Read complete or error: {e}")
                        break
            
            logger.info(f"Retrieved {len(raw_data)} bytes of raw data total")
            logger.debug(f"First 100 bytes (hex): {raw_data[:100].hex()}")
            logger.debug(f"First 100 bytes (ascii): {raw_data[:100]}")
            
            # Parse SCPI binary block format: #<n><length><data>
            # where <n> is number of digits in <length>
            if len(raw_data) < 2 or raw_data[0] != ord('#'):
                # Data might be direct binary (no SCPI header)
                # Check if it starts with WAVEDESC
                if raw_data[:8].startswith(b'WAVEDESC'):
                    logger.info("Waveform data is direct binary (starts with WAVEDESC)")
                    return raw_data
                else:
                    logger.warning("Waveform data doesn't start with '#' or 'WAVEDESC'")
                    logger.debug(f"First 20 bytes: {raw_data[:20]}")
                    # Try to find WAVEDESC in the data
                    wavedesc_pos = raw_data.find(b'WAVEDESC')
                    if wavedesc_pos >= 0:
                        logger.info(f"Found WAVEDESC at position {wavedesc_pos}, extracting from there")
                        return raw_data[wavedesc_pos:]
                    return raw_data
            
            # Parse SCPI binary block format
            if raw_data[0] == ord('#'):
                # Extract length digits
                num_digits = int(chr(raw_data[1]))
                if num_digits < 1 or num_digits > 9:
                    logger.warning(f"Invalid number of length digits: {num_digits}")
                    return raw_data
                
                # Extract length
                length_str = raw_data[2:2+num_digits].decode('ascii')
                data_length = int(length_str)
                
                # Extract actual binary data (skip header: '#' + num_digits + length_str)
                header_size = 2 + num_digits
                waveform_data = raw_data[header_size:header_size + data_length]
                
                # Handle potential newline terminator (SCPI standard)
                if len(raw_data) > header_size + data_length:
                    # Check if there's a newline after the data
                    remaining = raw_data[header_size + data_length:]
                    if remaining.startswith(b'\n') or remaining.startswith(b'\r\n'):
                        logger.debug("Removed newline terminator from waveform data")
                
                if len(waveform_data) != data_length:
                    logger.warning(f"Expected {data_length} bytes, got {len(waveform_data)} bytes")
                    # Use what we have if it's close
                    if abs(len(waveform_data) - data_length) <= 2:  # Allow small difference for terminator
                        logger.info(f"Using {len(waveform_data)} bytes (close to expected {data_length})")
                    else:
                        logger.error(f"Data length mismatch too large, cannot proceed")
                        return None
                
                logger.info(f"Extracted {len(waveform_data)} bytes of waveform data from SCPI binary block")
                return waveform_data
            else:
                # Direct binary data (already handled above)
                return raw_data
            
        finally:
            # Restore original timeout
            oscilloscope.timeout = original_timeout
                
    except Exception as e:
        logger.error(f"Error retrieving waveform: {e}", exc_info=True)
        return None


def plot_waveform(
    time_values: List[float], 
    voltage_values: List[float], 
    descriptor: dict,
    steady_state_start: Optional[int] = None,
    steady_state_end: Optional[int] = None,
    steady_state_avg: Optional[float] = None
) -> None:
    """Plot waveform data vs time with decimation.
    
    Args:
        time_values: List of time values in seconds
        voltage_values: List of voltage/current values
        descriptor: Waveform descriptor dictionary
        steady_state_start: Optional start index of steady state region
        steady_state_end: Optional end index of steady state region (exclusive)
        steady_state_avg: Optional average voltage in steady state region
    """
    if not matplotlib_available:
        logger.warning("Matplotlib not available - skipping plot generation")
        logger.warning("Install matplotlib to enable plotting: pip install matplotlib")
        return
    
    if not time_values or not voltage_values:
        logger.warning("No data available for plotting")
        return
    
    try:
        # Decimate data for plotting (max 10000 points for performance)
        max_plot_points = 10000
        total_points = len(voltage_values)
        
        if total_points > max_plot_points:
            decimation_factor = total_points // max_plot_points
            logger.info(f"Decimating data: using every {decimation_factor}th point for plotting "
                       f"({total_points} -> {total_points // decimation_factor} points)")
            
            time_plot = time_values[::decimation_factor]
            voltage_plot = voltage_values[::decimation_factor]
        else:
            time_plot = time_values
            voltage_plot = voltage_values
            logger.info(f"Plotting all {total_points} data points")
        
        # Create figure
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Plot waveform
        ax.plot(time_plot, voltage_plot, 'b-', linewidth=0.5, alpha=0.7, label='Channel 1')
        
        # Mark steady state region if provided
        if steady_state_start is not None and steady_state_end is not None:
            # Get time range for steady state region
            steady_time_start = time_values[steady_state_start]
            steady_time_end = time_values[steady_state_end - 1] if steady_state_end > 0 else time_values[-1]
            
            # Get voltage range for shading
            y_min = min(voltage_values)
            y_max = max(voltage_values)
            y_range = y_max - y_min
            if y_range == 0:
                y_range = 1.0  # Avoid division by zero
            
            # Shade the steady state region
            ax.axvspan(steady_time_start, steady_time_end, 
                      alpha=0.2, color='green', label='Steady State Region')
            
            # Add vertical lines at boundaries (only label the first one to avoid duplicates)
            ax.axvline(steady_time_start, color='green', linestyle='--', 
                     linewidth=1.5, alpha=0.7, label='Steady State Boundaries')
            ax.axvline(steady_time_end, color='green', linestyle='--', 
                     linewidth=1.5, alpha=0.7)
            
            # Add horizontal line for average if provided
            if steady_state_avg is not None:
                ax.axhline(steady_state_avg, color='red', linestyle='-', 
                         linewidth=1.5, alpha=0.8, label=f'Steady State Avg: {steady_state_avg:.6f} V')
        
        # Set labels and title
        instrument_name = descriptor.get('INSTRUMENT_NAME', 'Oscilloscope')
        trace_label = descriptor.get('TRACE_LABEL', 'Channel 1')
        if trace_label:
            title = f"{instrument_name} - {trace_label} Waveform"
        else:
            title = f"{instrument_name} - Channel 1 Waveform"
        
        # Add filter info to title if steady state analysis was performed (indicates filtered data)
        if steady_state_start is not None:
            title = f"{title} (10kHz Low-Pass Filtered)"
        
        ax.set_xlabel('Time (seconds)', fontsize=12)
        ax.set_ylabel('Voltage (V)', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')
        
        # Add statistics text box
        stats_text = (f"Points: {total_points}\n"
                     f"Duration: {max(time_values) - min(time_values):.6f} s\n"
                     f"Voltage Range: [{min(voltage_values):.3f}, {max(voltage_values):.3f}] V\n"
                     f"Vertical Gain: {descriptor['VERTICAL_GAIN']:.6e}\n"
                     f"Vertical Offset: {descriptor['VERTICAL_OFFSET']:.6e}")
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=9, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # Adjust layout
        plt.tight_layout()
        
        # Save plot to file
        plot_filename = f'channel1_waveform_{int(time.time())}.png'
        plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
        logger.info(f"Plot saved to: {plot_filename}")
        print(f"\nPlot saved to: {plot_filename}")
        
        # Show plot (blocking to ensure window stays open)
        try:
            # Check if we have a display
            has_display = ('DISPLAY' in os.environ or 
                         sys.platform == 'win32' or 
                         sys.platform == 'darwin')
            
            if has_display:
                logger.info("Displaying plot window...")
                print("\n" + "=" * 70)
                print("DISPLAYING PLOT WINDOW")
                print("=" * 70)
                print("A plot window should appear showing Channel 1 waveform vs time.")
                print("Close the plot window to continue.")
                print("=" * 70 + "\n")
                plt.show(block=True)  # Block to keep window open until user closes it
                logger.info("Plot window closed by user")
                print("Plot window closed.\n")
            else:
                plt.close()
                logger.info("No display available - plot saved only")
                print("No display available - plot saved to file only")
        except Exception as e:
            # If display is not available, just save the file
            plt.close()
            logger.warning(f"Could not display plot (saved to file): {e}")
            print(f"Could not display plot window: {e}")
            print(f"Plot saved to file: {plot_filename}")
        
    except Exception as e:
        logger.error(f"Failed to create plot: {e}", exc_info=True)
        try:
            plt.close('all')
        except Exception:
            pass


def main():
    """Main entry point."""
    logger.info("=" * 70)
    logger.info("Oscilloscope Waveform Data Retrieval")
    logger.info("=" * 70)
    
    # Initialize oscilloscope service
    try:
        oscilloscope_service = OscilloscopeService()
        if oscilloscope_service.resource_manager is None:
            logger.error("OscilloscopeService: PyVISA ResourceManager not available")
            return 1
        
        # Scan for devices
        devices = oscilloscope_service.scan_for_devices()
        if not devices:
            logger.error("No oscilloscope devices found")
            return 1
        
        logger.info(f"Found {len(devices)} oscilloscope device(s)")
        osc_resource = devices[0]
        logger.info(f"Connecting to: {osc_resource}")
        
        if not oscilloscope_service.connect(osc_resource):
            logger.error("Failed to connect to oscilloscope")
            return 1
        
        device_info = oscilloscope_service.get_device_info()
        if device_info:
            logger.info(f"Connected to oscilloscope: {device_info.strip()}")
        
        # Retrieve waveform data
        waveform_data = retrieve_waveform(oscilloscope_service)
        
        if waveform_data is None:
            logger.error("Failed to retrieve waveform data")
            oscilloscope_service.cleanup()
            return 1
        
        logger.info(f"Retrieved {len(waveform_data)} bytes of waveform data")
        
        # Query vertical gain and offset from oscilloscope
        logger.info("Querying vertical gain and offset from oscilloscope...")
        vertical_gain = query_vertical_gain(oscilloscope_service)
        vertical_offset = query_vertical_offset(oscilloscope_service)
        
        if vertical_gain is not None:
            logger.info(f"Queried C1:VDIV? = {vertical_gain}")
        else:
            logger.warning("Failed to query C1:VDIV?, will use value from waveform descriptor")
        
        if vertical_offset is not None:
            logger.info(f"Queried C1:OFST? = {vertical_offset}")
        else:
            logger.warning("Failed to query C1:OFST?, will use value from waveform descriptor")
        
        # Decode waveform data
        try:
            decoder = WaveformDecoder(waveform_data)
            descriptor, time_values, voltage_values = decoder.decode(
                vertical_gain=vertical_gain,
                vertical_offset=vertical_offset
            )
            
            logger.info("=" * 70)
            logger.info("Waveform Decoding Results")
            logger.info("=" * 70)
            logger.info(f"Instrument: {descriptor.get('INSTRUMENT_NAME', 'Unknown')}")
            logger.info(f"Trace Label: {descriptor.get('TRACE_LABEL', 'Unknown')}")
            logger.info(f"Data Format: {'BYTE' if descriptor['COMM_TYPE'] == 0 else 'WORD'}")
            logger.info(f"Number of Points: {len(voltage_values)}")
            
            # Show which values were used
            used_gain = vertical_gain if vertical_gain is not None else descriptor['VERTICAL_GAIN']
            used_offset = vertical_offset if vertical_offset is not None else descriptor['VERTICAL_OFFSET']
            logger.info(f"Vertical Gain (used): {used_gain:.6e}")
            logger.info(f"Vertical Offset (used): {used_offset:.6e}")
            if vertical_gain is not None:
                logger.info(f"  (from C1:VDIV?, descriptor value was: {descriptor['VERTICAL_GAIN']:.6e})")
            if vertical_offset is not None:
                logger.info(f"  (from C1:OFST?, descriptor value was: {descriptor['VERTICAL_OFFSET']:.6e})")
            logger.info(f"Horizontal Interval: {descriptor['HORIZ_INTERVAL']:.6e} s")
            logger.info(f"Horizontal Offset: {descriptor['HORIZ_OFFSET']:.6e} s")
            
            if voltage_values:
                logger.info(f"Voltage Range: [{min(voltage_values):.6f}, {max(voltage_values):.6f}]")
                logger.info(f"Time Range: [{min(time_values):.6f}, {max(time_values):.6f}] s")
                logger.info(f"Duration: {max(time_values) - min(time_values):.6f} s")
            
            # Print first few data points as example
            logger.info("")
            logger.info("First 10 data points:")
            for i in range(min(10, len(voltage_values))):
                logger.info(f"  Point {i}: t={time_values[i]:.6f} s, V={voltage_values[i]:.6f}")
            
            logger.info("=" * 70)
            logger.info("Waveform data decoded successfully!")
            
            # Apply 10kHz low-pass filter to the waveform
            logger.info("")
            logger.info("=" * 70)
            logger.info("Applying 10kHz Low-Pass Filter")
            logger.info("=" * 70)
            try:
                filtered_voltage_values = apply_lowpass_filter(
                    time_values, voltage_values, cutoff_freq=10000.0
                )
                logger.info(f"Filter applied successfully. Original data points: {len(voltage_values)}, "
                           f"Filtered data points: {len(filtered_voltage_values)}")
            except Exception as e:
                logger.error(f"Failed to apply filter: {e}", exc_info=True)
                logger.warning("Using unfiltered data for analysis")
                filtered_voltage_values = voltage_values
            
            # Analyze steady state region on filtered data
            steady_start = None
            steady_end = None
            steady_avg = None
            steady_std = None
            
            logger.info("")
            logger.info("=" * 70)
            logger.info("Steady State Analysis (on Filtered Data)")
            logger.info("=" * 70)
            try:
                # Use more lenient parameters for steady state detection
                # Skip more initial data (30%) to ensure we're past the ramp-up
                steady_start, steady_end, steady_avg, steady_std = analyze_steady_state(
                    time_values, filtered_voltage_values,
                    variance_threshold_percent=5.0,  # More lenient: 5% instead of 1%
                    skip_initial_percent=30.0  # Skip first 30% to avoid transients and ramp-up
                )
                
                steady_time_start = time_values[steady_start]
                steady_time_end = time_values[steady_end - 1] if steady_end > 0 else time_values[-1]
                steady_duration = steady_time_end - steady_time_start
                steady_points = steady_end - steady_start
                
                logger.info(f"Steady State Region Detected:")
                logger.info(f"  Start Index: {steady_start}")
                logger.info(f"  End Index: {steady_end} (exclusive)")
                logger.info(f"  Time Range: [{steady_time_start:.6f}, {steady_time_end:.6f}] s")
                logger.info(f"  Duration: {steady_duration:.6f} s")
                logger.info(f"  Number of Points: {steady_points} ({100.0 * steady_points / len(voltage_values):.1f}% of total)")
                logger.info(f"  Average Voltage: {steady_avg:.6f} V")
                logger.info(f"  Standard Deviation: {steady_std:.6f} V")
                if abs(steady_avg) > 1e-10:
                    cv_percent = abs(steady_std / steady_avg) * 100
                    logger.info(f"  Coefficient of Variation: {cv_percent:.3f}%")
                
                # Print summary
                print("\n" + "=" * 70)
                print("STEADY STATE ANALYSIS RESULTS")
                print("=" * 70)
                print(f"Steady State Average: {steady_avg:.6f} V")
                print(f"Standard Deviation: {steady_std:.6e} V")
                print(f"Steady State Region: {steady_time_start:.6f} s to {steady_time_end:.6f} s")
                print(f"Duration: {steady_duration:.6f} s ({steady_points} points)")
                print("=" * 70 + "\n")
                
            except Exception as e:
                logger.error(f"Failed to analyze steady state: {e}", exc_info=True)
            
            # Plot the filtered waveform data with steady state region marked
            plot_waveform(
                time_values, 
                filtered_voltage_values, 
                descriptor,
                steady_state_start=steady_start,
                steady_state_end=steady_end,
                steady_state_avg=steady_avg
            )
            
        except Exception as e:
            logger.error(f"Failed to decode waveform data: {e}", exc_info=True)
            oscilloscope_service.cleanup()
            return 1
        
        # Cleanup
        oscilloscope_service.cleanup()
        logger.info("Disconnected from oscilloscope")
        
        return 0
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())

