#!/usr/bin/env python3
"""
Script to capture screenshots of all GUI tabs and save them to docs/gui_screenshots/

This script:
1. Launches the GUI application
2. Waits for it to fully initialize
3. Iterates through all main tabs
4. For CAN Data View, also captures inner tabs
5. Saves screenshots as PNG files
"""

import sys
import os
import time
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from PySide6 import QtWidgets, QtCore, QtGui
from host_gui.base_gui import BaseGUI

def capture_window_screenshot(window, output_path):
    """Capture a screenshot of the entire window."""
    pixmap = window.grab()
    pixmap.save(str(output_path), "PNG")
    print(f"Saved screenshot: {output_path}")

def capture_gui_screenshots():
    """Main function to capture all GUI screenshots."""
    # Create output directory
    output_dir = repo_root / "docs" / "gui_screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    # Create Qt application
    app = QtWidgets.QApplication(sys.argv)
    
    # Create and show GUI
    print("Initializing GUI...")
    window = BaseGUI()
    window.show()
    
    # Process events to ensure window is fully rendered
    app.processEvents()
    time.sleep(1)  # Give it a moment to fully render
    
    # Resize window to a standard size for consistent screenshots
    window.resize(1400, 900)
    app.processEvents()
    time.sleep(0.5)
    
    # Get main tabs widget
    if not hasattr(window, 'tabs_main'):
        print("Error: Could not find tabs_main widget")
        return
    
    tabs_main = window.tabs_main
    num_tabs = tabs_main.count()
    print(f"Found {num_tabs} main tabs")
    
    # Capture each main tab
    for i in range(num_tabs):
        tab_name = tabs_main.tabText(i)
        print(f"\nCapturing tab {i+1}/{num_tabs}: {tab_name}")
        
        # Switch to this tab
        tabs_main.setCurrentIndex(i)
        app.processEvents()
        time.sleep(0.3)  # Wait for tab to render
        
        # Create safe filename from tab name
        safe_name = tab_name.replace(' ', '_').replace('/', '_')
        filename = f"{i+1:02d}_{safe_name}.png"
        output_path = output_dir / filename
        
        # Capture screenshot
        capture_window_screenshot(window, output_path)
        
        # Special handling for CAN Data View tab - capture inner tabs
        if tab_name == "CAN Data View":
            print("  Capturing inner tabs for CAN Data View...")
            
            # Try to find inner tab widget
            inner_tabs = None
            try:
                # Look for inner QTabWidget in CAN Data View
                can_tab_widget = tabs_main.widget(i)
                for child in can_tab_widget.findChildren(QtWidgets.QTabWidget):
                    if child.count() > 0:
                        inner_tabs = child
                        break
            except Exception as e:
                print(f"  Could not find inner tabs: {e}")
            
            if inner_tabs:
                num_inner = inner_tabs.count()
                print(f"  Found {num_inner} inner tabs")
                
                for j in range(num_inner):
                    inner_tab_name = inner_tabs.tabText(j)
                    print(f"    Capturing inner tab {j+1}/{num_inner}: {inner_tab_name}")
                    
                    # Switch to inner tab
                    inner_tabs.setCurrentIndex(j)
                    app.processEvents()
                    time.sleep(0.3)
                    
                    # Create filename for inner tab
                    safe_inner_name = inner_tab_name.replace(' ', '_').replace('/', '_')
                    inner_filename = f"{i+1:02d}_{safe_name}_inner_{j+1:02d}_{safe_inner_name}.png"
                    inner_output_path = output_dir / inner_filename
                    
                    # Capture screenshot
                    capture_window_screenshot(window, inner_output_path)
    
    print(f"\n✓ All screenshots saved to: {output_dir}")
    print("Closing GUI...")
    
    # Quit application (this will trigger closeEvent)
    app.quit()

if __name__ == "__main__":
    try:
        capture_gui_screenshots()
    except Exception as e:
        import traceback
        print(f"Error capturing screenshots: {e}")
        traceback.print_exc()
        sys.exit(1)

