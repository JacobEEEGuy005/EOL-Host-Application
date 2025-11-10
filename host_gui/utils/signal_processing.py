"""
Signal processing utilities for filtering and smoothing signals.

This module provides functions for applying digital filters to signal data,
including low-pass Butterworth filters and moving average filters.
"""
import logging
from typing import Union, List

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False

try:
    from scipy import signal
    scipy_available = True
except ImportError:
    signal = None
    scipy_available = False


def apply_lowpass_filter(
    time_values: Union[List[float], 'np.ndarray'],
    voltage_values: Union[List[float], 'np.ndarray'],
    cutoff_freq: float = 10000.0,
    filter_order: int = 4
) -> Union[List[float], 'np.ndarray']:
    """Apply a low-pass Butterworth filter to the voltage waveform.
    
    This function matches the filtering used in the test script to reduce noise
    before steady state analysis.
    
    Args:
        time_values: List or numpy array of time values in seconds
        voltage_values: List or numpy array of voltage values to filter
        cutoff_freq: Cutoff frequency in Hz (default 10kHz, matching test script)
        filter_order: Filter order (default 4)
        
    Returns:
        Filtered voltage values (same type as input)
    """
    if not voltage_values or len(voltage_values) < 10:
        logger.warning("Insufficient data points for filtering, returning original data")
        return voltage_values
    
    if not numpy_available:
        logger.warning("NumPy not available - cannot apply digital filter, returning unfiltered data")
        return voltage_values
    
    if not scipy_available:
        logger.warning("SciPy not available - using simple moving average filter as fallback")
        # Fallback to simple moving average
        return apply_moving_average_filter(voltage_values, window_size=10)
    
    # Convert to numpy arrays if needed
    if not isinstance(voltage_values, np.ndarray):
        voltages = np.array(voltage_values, dtype=np.float64)
        return_list = True
    else:
        voltages = voltage_values.astype(np.float64) if voltage_values.dtype != np.float64 else voltage_values
        return_list = False
    
    if not isinstance(time_values, np.ndarray):
        times = np.array(time_values, dtype=np.float64)
    else:
        times = time_values.astype(np.float64) if time_values.dtype != np.float64 else time_values
    
    # Calculate sampling frequency
    if len(time_values) < 2:
        logger.warning("Need at least 2 time points to calculate sampling frequency, returning unfiltered data")
        return voltage_values
    
    dt = times[1] - times[0]
    if dt <= 0:
        # Try to calculate from average
        dt = (times[-1] - times[0]) / (len(times) - 1)
        if dt <= 0:
            logger.warning("Invalid time values for filtering, returning unfiltered data")
            return voltage_values
    
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
        
        # Apply filter using filtfilt for zero-phase filtering
        filtered_voltages = signal.filtfilt(b, a, voltages)
        
        logger.info(f"Filter applied successfully using filtfilt (zero-phase filtering), "
                   f"filtered {len(filtered_voltages)} points")
        
        if return_list:
            return filtered_voltages.tolist()
        else:
            return filtered_voltages
        
    except Exception as e:
        logger.error(f"Error applying filter: {e}", exc_info=True)
        logger.warning("Returning unfiltered data")
        return voltage_values


def apply_moving_average_filter(voltage_values: Union[List[float], 'np.ndarray'], window_size: int = 10) -> Union[List[float], 'np.ndarray']:
    """Apply a simple moving average filter (fallback when scipy is not available).
    
    Args:
        voltage_values: List or numpy array of voltage values
        window_size: Size of moving average window
        
    Returns:
        Filtered voltage values (same type as input)
    """
    if len(voltage_values) < window_size:
        return voltage_values
    
    return_list = not isinstance(voltage_values, np.ndarray)
    
    # Optimized: use NumPy convolution if available (much faster)
    if numpy_available:
        window = np.ones(window_size, dtype=np.float32) / window_size
        if isinstance(voltage_values, np.ndarray):
            filtered = np.convolve(voltage_values, window, mode='same')
            return filtered
        else:
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

