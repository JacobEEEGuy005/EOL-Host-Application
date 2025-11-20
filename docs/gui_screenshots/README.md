# GUI Screenshots

This folder contains screenshots of all tabs and views in the EOL Host Application GUI.

## Screenshots

### Main Tabs

1. **01_Home.png** - Welcome/home tab with application overview
2. **02_CAN_Data_View.png** - Main CAN Data View tab
3. **03_EOL_H_W_Configuration.png** - EOL Hardware Configuration tab
4. **04_Oscilloscope_Configuration.png** - Oscilloscope Configuration tab
5. **05_Test_Configurator.png** - Test Configurator tab for creating test profiles
6. **06_Test_Status.png** - Test Status tab for executing tests and viewing results
7. **07_Test_Report.png** - Test Report tab for viewing test execution reports

### CAN Data View Inner Tabs

The CAN Data View tab contains several sub-tabs:

- **02_CAN_Data_View_inner_01_DBC_Manager.png** - DBC file management interface
- **02_CAN_Data_View_inner_02_Live_Data.png** - Live CAN frame monitoring
- **02_CAN_Data_View_inner_03_Signal_View.png** - Decoded signal values from DBC
- **02_CAN_Data_View_inner_04_Send_Data.png** - Manual CAN frame transmission
- **02_CAN_Data_View_inner_05_Settings.png** - CAN adapter settings and configuration

## Generating Screenshots

To regenerate these screenshots, run:

```bash
.venv/bin/python scripts/capture_gui_screenshots.py
```

**Note:** This requires a display server (X11) to be available. The script will automatically capture all tabs and save them to this directory.

## Last Updated

Screenshots generated on: 2025-11-20

