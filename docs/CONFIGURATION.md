# Configuration Management

## Overview

The EOL Host Application uses a centralized configuration management system (`ConfigManager`) that supports multiple configuration sources with priority ordering. This allows for flexible configuration while maintaining backwards compatibility with environment variables.

## Configuration Sources (Priority Order)

1. **JSON Config File** (highest priority)
   - User config: `~/.eol_host/config.json`
   - Project config: `backend/parameters.json`
2. **Environment Variables** (backwards compatibility)
   - `CAN_CHANNEL` or `PCAN_CHANNEL`
   - `CAN_BITRATE` or `PCAN_BITRATE`
   - `LOG_LEVEL`
3. **Default Values** (lowest priority)
   - Defined in `host_gui/constants.py`

## Configuration Sections

### CanSettings

CAN bus configuration settings.

**Fields**:
- `channel` (str): CAN channel/interface identifier (e.g., '0', 'can0')
  - Default: `CAN_CHANNEL_DEFAULT` (from constants)
  - Environment: `CAN_CHANNEL` or `PCAN_CHANNEL`
- `bitrate` (int): CAN bitrate in kbps (e.g., 500 for 500kbps)
  - Default: `CAN_BITRATE_DEFAULT` (from constants)
  - Environment: `CAN_BITRATE` or `PCAN_BITRATE`
- `adapter_type` (str, optional): Preferred adapter type ('SimAdapter', 'PCAN', etc.)

**Example JSON**:
```json
{
  "can_settings": {
    "channel": "0",
    "bitrate": 500,
    "adapter_type": "PCAN"
  }
}
```

### UISettings

User interface configuration settings.

**Fields**:
- `window_width` (int): Main window width in pixels
  - Default: `WINDOW_WIDTH_DEFAULT` (1100)
  - Minimum: 400
- `window_height` (int): Main window height in pixels
  - Default: `WINDOW_HEIGHT_DEFAULT` (700)
  - Minimum: 300
- `max_messages` (int): Maximum messages to keep in message log
  - Default: `MAX_MESSAGES_DEFAULT` (50)
  - Minimum: 10
- `max_frames` (int): Maximum frames to keep in frame table
  - Default: `MAX_FRAMES_DEFAULT` (50)
  - Minimum: 10
- `theme` (str, optional): UI theme preference (for future use)

**Example JSON**:
```json
{
  "ui_settings": {
    "window_width": 1200,
    "window_height": 800,
    "max_messages": 100,
    "max_frames": 100,
    "theme": "dark"
  }
}
```

### AppSettings

Application-level configuration settings.

**Fields**:
- `log_level` (str): Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
  - Default: 'INFO'
  - Environment: `LOG_LEVEL`
- `data_dir` (str, optional): Directory for test profiles and DBC files
  - Default: `backend/data` (relative to repo root)
- `dbc_dir` (str, optional): Directory for DBC files
  - Default: `{data_dir}/dbcs`
- `test_dir` (str, optional): Directory for test profiles
  - Default: `{data_dir}/tests`
- `autosave` (bool): Whether to autosave test configurations
  - Default: false
- `autosave_interval` (int): Autosave interval in seconds (if autosave enabled)
  - Default: 300 (5 minutes)

**Example JSON**:
```json
{
  "app_settings": {
    "log_level": "DEBUG",
    "data_dir": "/path/to/data",
    "dbc_dir": "/path/to/dbcs",
    "test_dir": "/path/to/tests",
    "autosave": true,
    "autosave_interval": 300
  }
}
```

## Complete Configuration File Example

```json
{
  "can_settings": {
    "channel": "0",
    "bitrate": 500,
    "adapter_type": "PCAN"
  },
  "ui_settings": {
    "window_width": 1200,
    "window_height": 800,
    "max_messages": 100,
    "max_frames": 100
  },
  "app_settings": {
    "log_level": "INFO",
    "data_dir": "/path/to/data",
    "autosave": false,
    "autosave_interval": 300
  }
}
```

## Using ConfigManager

### Initialization

```python
from host_gui.config import ConfigManager

# Initialize with default locations
config = ConfigManager()

# Or specify a config file
config = ConfigManager(config_file='/path/to/config.json')
```

### Accessing Configuration

```python
# CAN settings
channel = config.can_settings.channel
bitrate = config.can_settings.bitrate

# UI settings
window_width = config.ui_settings.window_width
max_messages = config.ui_settings.max_messages

# App settings
log_level = config.app_settings.log_level
data_dir = config.app_settings.get_data_dir()
dbc_dir = config.app_settings.get_dbc_dir()
test_dir = config.app_settings.get_test_dir()
```

### Saving Configuration

```python
# Save to default location (~/.eol_host/config.json)
config.save_to_file()

# Or specify a location
config.save_to_file('/path/to/config.json')
```

### Validation

```python
errors = config.validate()
if errors:
    print(f"Configuration errors: {errors}")
```

## User Preferences (QSettings)

The `ConfigManager` also provides methods for storing user preferences using Qt QSettings:

### Window Geometry

```python
# Save window geometry
config.save_window_geometry(window.saveGeometry())

# Restore window geometry
geometry = config.restore_window_geometry()
if geometry:
    window.restoreGeometry(geometry)
```

### Recent Files

```python
# Save recent files
config.save_recent_files(['/path/to/file1.json', '/path/to/file2.json'], max_count=10)

# Get recent files
recent_files = config.get_recent_files()
```

### Custom Preferences

```python
# Save a preference
config.save_user_preference('last_test_dir', '/path/to/tests')

# Get a preference
last_test_dir = config.get_user_preference('last_test_dir', default='/default/path')
```

## Environment Variables (Backwards Compatibility)

For backwards compatibility, the following environment variables are supported:

- `CAN_CHANNEL` or `PCAN_CHANNEL`: CAN channel/interface
- `CAN_BITRATE` or `PCAN_BITRATE`: CAN bitrate in kbps
- `LOG_LEVEL`: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')

**Note**: Environment variables have lower priority than JSON config files but higher priority than defaults.

## Configuration in BaseGUI

The `BaseGUI` class uses `ConfigManager` for configuration:

```python
from host_gui.config import ConfigManager

class BaseGUI(QtWidgets.QMainWindow):
    def __init__(self):
        # Initialize config manager
        self.config = ConfigManager()
        
        # Use configuration
        channel = self.config.can_settings.channel
        bitrate = self.config.can_settings.bitrate
        
        # Initialize services with config
        self.can_service = CanService(channel=channel, bitrate=bitrate)
```

## Migration from Environment Variables

To migrate from environment variables to JSON config files:

1. Create a config file at `~/.eol_host/config.json`:
```json
{
  "can_settings": {
    "channel": "0",
    "bitrate": 500
  },
  "app_settings": {
    "log_level": "INFO"
  }
}
```

2. Remove environment variables (optional, they still work as fallback)

3. The application will automatically use the config file if it exists

## Best Practices

1. **Use JSON Config Files**: Prefer JSON config files over environment variables for persistent configuration
2. **User Config Directory**: Store user-specific config in `~/.eol_host/config.json`
3. **Project Config**: Store project-wide defaults in `backend/parameters.json`
4. **Environment Variables**: Use environment variables for temporary overrides or CI/CD
5. **Validation**: Always validate configuration after loading
6. **Defaults**: Provide sensible defaults for all settings
7. **Documentation**: Document all configuration options and their purposes

## Related Documentation

- [Service Architecture](SERVICE_ARCHITECTURE.md) - Service initialization with configuration
- [Exception Handling](EXCEPTION_HANDLING.md) - ConfigurationError exception

