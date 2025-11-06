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
        
        # Calculate time values
        horiz_interval = descriptor['HORIZ_INTERVAL']
        horiz_offset = descriptor['HORIZ_OFFSET']
        
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


def plot_waveform(time_values: List[float], voltage_values: List[float], descriptor: dict) -> None:
    """Plot waveform data vs time with decimation.
    
    Args:
        time_values: List of time values in seconds
        voltage_values: List of voltage/current values
        descriptor: Waveform descriptor dictionary
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
        
        # Set labels and title
        instrument_name = descriptor.get('INSTRUMENT_NAME', 'Oscilloscope')
        trace_label = descriptor.get('TRACE_LABEL', 'Channel 1')
        if trace_label:
            title = f"{instrument_name} - {trace_label} Waveform"
        else:
            title = f"{instrument_name} - Channel 1 Waveform"
        
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
            
            # Plot the waveform data
            plot_waveform(time_values, voltage_values, descriptor)
            
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

