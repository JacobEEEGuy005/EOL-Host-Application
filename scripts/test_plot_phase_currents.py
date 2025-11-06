#!/usr/bin/env python3
"""Test script to verify phase current plotting functionality."""

import time
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import matplotlib for plotting (optional)
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib_available = True
except ImportError:
    matplotlib = None
    plt = None
    matplotlib_available = False
    print("ERROR: Matplotlib not available. Install it with: pip install matplotlib")
    sys.exit(1)

def plot_phase_currents(timestamps, phase_v_values, phase_w_values, 
                         ramp_up_end, ramp_down_start):
    """Plot PhaseVCurrent and PhaseWCurrent vs time."""
    if not matplotlib_available:
        print("Matplotlib not available")
        return
    
    if not timestamps or not phase_v_values or not phase_w_values:
        print("No data available for plotting")
        return
    
    try:
        # Calculate relative time (seconds from first timestamp)
        if len(timestamps) > 1:
            start_time = timestamps[0]
            time_relative = [(t - start_time) for t in timestamps]
        else:
            time_relative = [0.0]
        
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        
        # Plot Phase V Current
        ax1.plot(time_relative, phase_v_values, 'b-', linewidth=1.5, label='Phase V Current', alpha=0.7)
        if ramp_up_end > 0 and ramp_up_end < len(time_relative):
            ax1.axvspan(time_relative[0], time_relative[ramp_up_end],
                       alpha=0.2, color='red', label='Ramp Up (discarded)')
        if ramp_down_start < len(time_relative):
            ax1.axvspan(time_relative[ramp_down_start], time_relative[-1],
                       alpha=0.2, color='red', label='Ramp Down (discarded)')
        if ramp_up_end < ramp_down_start and ramp_up_end < len(time_relative):
            end_idx = min(ramp_down_start, len(time_relative))
            ax1.axvspan(time_relative[ramp_up_end], time_relative[end_idx-1],
                       alpha=0.2, color='green', label='Steady State')
        
        ax1.set_ylabel('Phase V Current (A)', fontsize=12)
        ax1.set_title('Phase Currents vs Time (from CAN Data)', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='best')
        
        # Plot Phase W Current
        ax2.plot(time_relative, phase_w_values, 'r-', linewidth=1.5, label='Phase W Current', alpha=0.7)
        if ramp_up_end > 0 and ramp_up_end < len(time_relative):
            ax2.axvspan(time_relative[0], time_relative[ramp_up_end],
                       alpha=0.2, color='red', label='Ramp Up (discarded)')
        if ramp_down_start < len(time_relative):
            ax2.axvspan(time_relative[ramp_down_start], time_relative[-1],
                       alpha=0.2, color='red', label='Ramp Down (discarded)')
        if ramp_up_end < ramp_down_start and ramp_up_end < len(time_relative):
            end_idx = min(ramp_down_start, len(time_relative))
            ax2.axvspan(time_relative[ramp_up_end], time_relative[end_idx-1],
                       alpha=0.2, color='green', label='Steady State')
        
        ax2.set_xlabel('Time (seconds)', fontsize=12)
        ax2.set_ylabel('Phase W Current (A)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='best')
        
        # Adjust layout
        plt.tight_layout()
        
        # Save plot to file
        plot_filename = f'phase_currents_plot_test_{int(time.time())}.png'
        plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
        print(f"Plot saved to: {plot_filename}")
        
        # Show plot (blocking to ensure window stays open)
        print("Displaying plot window...")
        print("Close the plot window to continue.")
        plt.show(block=True)
        print("Plot window closed.")
        
    except Exception as e:
        print(f"Failed to create plot: {e}")
        import traceback
        traceback.print_exc()
        try:
            plt.close('all')
        except Exception:
            pass

def main():
    """Generate mock data and test plotting."""
    print("Generating mock phase current data...")
    
    # Generate mock data: 100 data points over 4 seconds
    start_time = time.time()
    timestamps = []
    phase_v_values = []
    phase_w_values = []
    
    # Simulate ramp up (0-0.8s), steady state (0.8-3.2s), ramp down (3.2-4s)
    for i in range(100):
        t = start_time + (i / 100.0) * 4.0
        timestamps.append(t)
        
        if i < 20:  # Ramp up
            phase_v = 50.0 * (i / 20.0) + (i * 0.1)  # Ramp from 0 to ~50
            phase_w = -50.0 * (i / 20.0) - (i * 0.1)  # Ramp from 0 to ~-50
        elif i < 80:  # Steady state
            phase_v = 50.0 + (i % 10 - 5) * 0.2  # Steady around 50 with small noise
            phase_w = -50.0 - (i % 10 - 5) * 0.2  # Steady around -50 with small noise
        else:  # Ramp down
            phase_v = 50.0 * (1.0 - (i - 80) / 20.0)  # Ramp down from 50 to 0
            phase_w = -50.0 * (1.0 - (i - 80) / 20.0)  # Ramp down from -50 to 0
        
        phase_v_values.append(phase_v)
        phase_w_values.append(phase_w)
    
    # Calculate ramp boundaries (20% and 80%)
    total_points = len(phase_v_values)
    ramp_up_end = int(total_points * 0.2)  # 20 points
    ramp_down_start = int(total_points * 0.8)  # 80 points
    
    print(f"Mock data generated: {total_points} points")
    print(f"Ramp up end: {ramp_up_end}, Ramp down start: {ramp_down_start}")
    print(f"Steady state points: {ramp_down_start - ramp_up_end}")
    
    # Plot the data
    plot_phase_currents(timestamps, phase_v_values, phase_w_values, 
                       ramp_up_end, ramp_down_start)

if __name__ == '__main__':
    main()

