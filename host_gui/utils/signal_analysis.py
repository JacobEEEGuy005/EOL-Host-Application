"""
Signal analysis utilities for steady-state detection and statistical analysis.

This module provides functions for analyzing signal data to identify steady-state
regions and compute statistical properties.
"""
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False


def analyze_steady_state_can(
    timestamps: List[float],
    values: List[float],
    window_size: Optional[int] = None,
    variance_threshold_percent: float = 5.0,
    skip_initial_percent: float = 30.0
) -> Tuple[Optional[int], Optional[int], Optional[float], Optional[float]]:
    """Analyze CAN signal data to find steady state region and compute average.
    
    Args:
        timestamps: List of timestamps in seconds
        values: List of signal values
        window_size: Size of rolling window for variance calculation. If None, uses 1% of data points.
        variance_threshold_percent: Maximum coefficient of variation (std/mean * 100) for steady state
        skip_initial_percent: Percentage of initial data to skip when looking for steady state
        
    Returns:
        Tuple of (start_index, end_index, average_value, std_deviation) or (None, None, None, None) if insufficient data
    """
    if not values or len(values) < 10:
        logger.warning("Insufficient data points for steady state analysis")
        return (None, None, None, None)
    
    num_points = len(values)
    
    # Determine window size (1% of data points, minimum 10, maximum 2000)
    if window_size is None:
        window_size = max(10, min(2000, num_points // 100))
    
    # Skip initial transient period
    skip_points = int(num_points * skip_initial_percent / 100.0)
    search_start = max(skip_points, window_size)
    search_end = num_points - window_size
    
    if search_start >= search_end:
        search_start = window_size
        search_end = num_points - window_size
    
    if search_start >= search_end:
        search_start = 0
        search_end = num_points
    
    # Find region with lowest variance
    best_start = search_start
    best_variance = float('inf')
    best_mean = 0.0
    
    if numpy_available:
        values_array = np.array(values, dtype=np.float64)
        for start_idx in range(search_start, search_end):
            window_data = values_array[start_idx:start_idx + window_size]
            window_mean = float(np.mean(window_data))
            window_std = float(np.std(window_data))
            
            # Use coefficient of variation (CV) = std/mean * 100
            if abs(window_mean) > 1e-10:
                cv = abs(window_std / window_mean) * 100
            else:
                cv = window_std * 100
            
            if cv < variance_threshold_percent and window_std < best_variance:
                best_variance = window_std
                best_start = start_idx
                best_mean = window_mean
    else:
        # Manual calculation without numpy
        for start_idx in range(search_start, search_end):
            window_data = values[start_idx:start_idx + window_size]
            window_mean = sum(window_data) / len(window_data)
            window_variance = sum((x - window_mean) ** 2 for x in window_data) / len(window_data)
            window_std = window_variance ** 0.5
            
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
        if numpy_available:
            values_array = np.array(values, dtype=np.float64)
            for start_idx in range(search_start, search_end):
                window_data = values_array[start_idx:start_idx + window_size]
                window_std = float(np.std(window_data))
                if window_std < best_variance:
                    best_variance = window_std
                    best_start = start_idx
                    best_mean = float(np.mean(window_data))
        else:
            for start_idx in range(search_start, search_end):
                window_data = values[start_idx:start_idx + window_size]
                window_mean = sum(window_data) / len(window_data)
                window_variance = sum((x - window_mean) ** 2 for x in window_data) / len(window_data)
                window_std = window_variance ** 0.5
                if window_std < best_variance:
                    best_variance = window_std
                    best_start = start_idx
                    best_mean = window_mean
    
    # Extend steady state region forward and backward
    steady_start = best_start
    steady_end = best_start + window_size
    
    # Extend backward
    if numpy_available:
        values_array = np.array(values, dtype=np.float64)
        for i in range(best_start - 1, max(0, best_start - window_size), -1):
            test_window = values_array[i:steady_end]
            test_mean = float(np.mean(test_window))
            test_std = float(np.std(test_window))
            if abs(best_mean) > 1e-10:
                cv = abs(test_std / test_mean) * 100
            else:
                cv = test_std * 100
            if cv < variance_threshold_percent * 1.5:  # Slightly relaxed for extension
                steady_start = i
            else:
                break
    else:
        for i in range(best_start - 1, max(0, best_start - window_size), -1):
            test_window = values[i:steady_end]
            test_mean = sum(test_window) / len(test_window)
            test_variance = sum((x - test_mean) ** 2 for x in test_window) / len(test_window)
            test_std = test_variance ** 0.5
            if abs(best_mean) > 1e-10:
                cv = abs(test_std / test_mean) * 100
            else:
                cv = test_std * 100
            if cv < variance_threshold_percent * 1.5:
                steady_start = i
            else:
                break
    
    # Extend forward
    if numpy_available:
        for i in range(steady_end, min(num_points, steady_end + window_size)):
            test_window = values_array[steady_start:i + 1]
            test_mean = float(np.mean(test_window))
            test_std = float(np.std(test_window))
            if abs(best_mean) > 1e-10:
                cv = abs(test_std / test_mean) * 100
            else:
                cv = test_std * 100
            if cv < variance_threshold_percent * 1.5:
                steady_end = i + 1
            else:
                break
    else:
        for i in range(steady_end, min(num_points, steady_end + window_size)):
            test_window = values[steady_start:i + 1]
            test_mean = sum(test_window) / len(test_window)
            test_variance = sum((x - test_mean) ** 2 for x in test_window) / len(test_window)
            test_std = test_variance ** 0.5
            if abs(best_mean) > 1e-10:
                cv = abs(test_std / test_mean) * 100
            else:
                cv = test_std * 100
            if cv < variance_threshold_percent * 1.5:
                steady_end = i + 1
            else:
                break
    
    # Calculate final average and std
    steady_data = values[steady_start:steady_end]
    if not steady_data:
        return (None, None, None, None)
    
    if numpy_available:
        steady_array = np.array(steady_data, dtype=np.float64)
        avg = float(np.mean(steady_array))
        std = float(np.std(steady_array))
    else:
        avg = sum(steady_data) / len(steady_data)
        variance = sum((x - avg) ** 2 for x in steady_data) / len(steady_data)
        std = variance ** 0.5
    
    return (steady_start, steady_end, avg, std)

