"""
Configuration management for EOL Host GUI application.

This module provides centralized configuration management, supporting:
- Loading from JSON config files
- Environment variable fallback (backwards compatibility)
- Qt QSettings for user preferences (window position, recent files)
- Validation and type safety for all settings
"""

import os
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from pathlib import Path

from PySide6 import QtCore

from host_gui.constants import (
    CAN_CHANNEL_DEFAULT, CAN_BITRATE_DEFAULT,
    MAX_MESSAGES_DEFAULT, MAX_FRAMES_DEFAULT,
    WINDOW_WIDTH_DEFAULT, WINDOW_HEIGHT_DEFAULT
)

logger = logging.getLogger(__name__)


@dataclass
class CanSettings:
    """CAN bus configuration settings.
    
    Attributes:
        channel: CAN channel/interface identifier (e.g., '0', 'can0')
        bitrate: CAN bitrate in kbps (e.g., 500 for 500kbps)
        adapter_type: Preferred adapter type ('SimAdapter', 'PCAN', etc.)
    """
    channel: str = CAN_CHANNEL_DEFAULT
    bitrate: int = CAN_BITRATE_DEFAULT
    adapter_type: Optional[str] = None
    
    def validate(self) -> List[str]:
        """Validate settings and return list of error messages (empty if valid)."""
        errors = []
        if not self.channel or not isinstance(self.channel, str):
            errors.append("CAN channel must be a non-empty string")
        if not isinstance(self.bitrate, int) or self.bitrate <= 0:
            errors.append("CAN bitrate must be a positive integer")
        if self.adapter_type is not None and not isinstance(self.adapter_type, str):
            errors.append("Adapter type must be a string or None")
        return errors


@dataclass
class UISettings:
    """User interface configuration settings.
    
    Attributes:
        window_width: Main window width in pixels
        window_height: Main window height in pixels
        max_messages: Maximum messages to keep in message log
        max_frames: Maximum frames to keep in frame table
        theme: UI theme preference (optional, for future use)
    """
    window_width: int = WINDOW_WIDTH_DEFAULT
    window_height: int = WINDOW_HEIGHT_DEFAULT
    max_messages: int = MAX_MESSAGES_DEFAULT
    max_frames: int = MAX_FRAMES_DEFAULT
    theme: Optional[str] = None
    
    def validate(self) -> List[str]:
        """Validate settings and return list of error messages (empty if valid)."""
        errors = []
        if not isinstance(self.window_width, int) or self.window_width < 400:
            errors.append("Window width must be an integer >= 400")
        if not isinstance(self.window_height, int) or self.window_height < 300:
            errors.append("Window height must be an integer >= 300")
        if not isinstance(self.max_messages, int) or self.max_messages < 10:
            errors.append("Max messages must be an integer >= 10")
        if not isinstance(self.max_frames, int) or self.max_frames < 10:
            errors.append("Max frames must be an integer >= 10")
        return errors


@dataclass
class AppSettings:
    """Application-level configuration settings.
    
    Attributes:
        log_level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        data_dir: Directory for test profiles and DBC files
        dbc_dir: Directory for DBC files (defaults to data_dir/dbcs)
        test_dir: Directory for test profiles (defaults to data_dir/tests)
        autosave: Whether to autosave test configurations
        autosave_interval: Autosave interval in seconds (if autosave enabled)
    """
    log_level: str = 'INFO'
    data_dir: Optional[str] = None
    dbc_dir: Optional[str] = None
    test_dir: Optional[str] = None
    autosave: bool = False
    autosave_interval: int = 300  # 5 minutes
    
    def validate(self) -> List[str]:
        """Validate settings and return list of error messages (empty if valid)."""
        errors = []
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if self.log_level.upper() not in valid_levels:
            errors.append(f"Log level must be one of {valid_levels}")
        if self.autosave_interval < 0:
            errors.append("Autosave interval must be non-negative")
        return errors
    
    def get_data_dir(self) -> str:
        """Get the data directory, using default if not set."""
        if self.data_dir:
            return self.data_dir
        # Default to backend/data relative to repo root
        repo_root = Path(__file__).parent.parent
        return str(repo_root / 'backend' / 'data')
    
    def get_dbc_dir(self) -> str:
        """Get the DBC directory, using default if not set."""
        if self.dbc_dir:
            return self.dbc_dir
        return os.path.join(self.get_data_dir(), 'dbcs')
    
    def get_test_dir(self) -> str:
        """Get the test directory, using default if not set."""
        if self.test_dir:
            return self.test_dir
        return os.path.join(self.get_data_dir(), 'tests')


class ConfigManager:
    """Centralized configuration manager for EOL Host GUI.
    
    This class provides a single source of truth for all application configuration.
    It supports loading from multiple sources with priority:
    1. JSON config file (highest priority)
    2. Environment variables (backwards compatibility)
    3. Default values (lowest priority)
    
    User preferences (window position, recent files) are stored using Qt QSettings.
    
    Attributes:
        can_settings: CAN bus configuration
        ui_settings: User interface configuration
        app_settings: Application-level configuration
        _config_file: Path to JSON config file (if loaded)
        _qsettings: Qt QSettings instance for user preferences
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize ConfigManager.
        
        Args:
            config_file: Optional path to JSON config file. If None, will try:
                        - ~/.eol_host/config.json (user config)
                        - backend/parameters.json (project config)
        """
        self.can_settings = CanSettings()
        self.ui_settings = UISettings()
        self.app_settings = AppSettings()
        self._config_file: Optional[str] = config_file
        self._qsettings = QtCore.QSettings('ErgonLabs', 'EOLHost')
        
        # Load configuration
        self._load_from_environment()
        if config_file:
            self._load_from_file(config_file)
        else:
            self._load_from_default_locations()
        
        # Validate loaded configuration
        errors = self.validate()
        if errors:
            logger.warning(f"Configuration validation errors: {errors}")
            # Continue with defaults for invalid values
    
    def _load_from_environment(self) -> None:
        """Load configuration from environment variables (backwards compatibility)."""
        # CAN settings
        can_channel = os.environ.get('CAN_CHANNEL') or os.environ.get('PCAN_CHANNEL')
        if can_channel:
            self.can_settings.channel = can_channel
        
        can_bitrate = os.environ.get('CAN_BITRATE') or os.environ.get('PCAN_BITRATE')
        if can_bitrate:
            try:
                self.can_settings.bitrate = int(can_bitrate)
            except (ValueError, TypeError):
                logger.warning(f"Invalid CAN_BITRATE environment variable: {can_bitrate}")
        
        # App settings
        log_level = os.environ.get('LOG_LEVEL')
        if log_level:
            self.app_settings.log_level = log_level.upper()
    
    def _load_from_file(self, file_path: str) -> bool:
        """Load configuration from JSON file.
        
        Args:
            file_path: Path to JSON config file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        if not os.path.exists(file_path):
            logger.debug(f"Config file not found: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load CAN settings
            if 'can_settings' in data:
                can_data = data['can_settings']
                if 'channel' in can_data:
                    self.can_settings.channel = str(can_data['channel'])
                if 'bitrate' in can_data:
                    try:
                        self.can_settings.bitrate = int(can_data['bitrate'])
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid bitrate in config: {can_data['bitrate']}")
                if 'adapter_type' in can_data:
                    self.can_settings.adapter_type = can_data['adapter_type']
            
            # Load UI settings
            if 'ui_settings' in data:
                ui_data = data['ui_settings']
                if 'window_width' in ui_data:
                    self.ui_settings.window_width = int(ui_data['window_width'])
                if 'window_height' in ui_data:
                    self.ui_settings.window_height = int(ui_data['window_height'])
                if 'max_messages' in ui_data:
                    self.ui_settings.max_messages = int(ui_data['max_messages'])
                if 'max_frames' in ui_data:
                    self.ui_settings.max_frames = int(ui_data['max_frames'])
                if 'theme' in ui_data:
                    self.ui_settings.theme = ui_data['theme']
            
            # Load App settings
            if 'app_settings' in data:
                app_data = data['app_settings']
                if 'log_level' in app_data:
                    self.app_settings.log_level = str(app_data['log_level']).upper()
                if 'data_dir' in app_data:
                    self.app_settings.data_dir = app_data['data_dir']
                if 'dbc_dir' in app_data:
                    self.app_settings.dbc_dir = app_data['dbc_dir']
                if 'test_dir' in app_data:
                    self.app_settings.test_dir = app_data['test_dir']
                if 'autosave' in app_data:
                    self.app_settings.autosave = bool(app_data['autosave'])
                if 'autosave_interval' in app_data:
                    self.app_settings.autosave_interval = int(app_data['autosave_interval'])
            
            self._config_file = file_path
            logger.info(f"Loaded configuration from {file_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config file {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load config file {file_path}: {e}", exc_info=True)
            return False
    
    def _load_from_default_locations(self) -> None:
        """Try loading from default config file locations."""
        # Try user config directory first
        user_config_dir = Path.home() / '.eol_host'
        user_config_file = user_config_dir / 'config.json'
        if user_config_file.exists():
            self._load_from_file(str(user_config_file))
            return
        
        # Try project config file
        repo_root = Path(__file__).parent.parent
        project_config_file = repo_root / 'backend' / 'parameters.json'
        if project_config_file.exists():
            self._load_from_file(str(project_config_file))
    
    def save_to_file(self, file_path: Optional[str] = None) -> bool:
        """Save current configuration to JSON file.
        
        Args:
            file_path: Optional path to save to. If None, uses _config_file or creates user config.
            
        Returns:
            True if saved successfully, False otherwise
        """
        save_path = file_path or self._config_file
        if not save_path:
            # Default to user config directory
            user_config_dir = Path.home() / '.eol_host'
            user_config_dir.mkdir(exist_ok=True)
            save_path = str(user_config_dir / 'config.json')
        
        try:
            data = {
                'can_settings': asdict(self.can_settings),
                'ui_settings': asdict(self.ui_settings),
                'app_settings': asdict(self.app_settings)
            }
            
            # Remove None values
            for section in data.values():
                for key in list(section.keys()):
                    if section[key] is None:
                        del section[key]
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self._config_file = save_path
            logger.info(f"Saved configuration to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save config file {save_path}: {e}", exc_info=True)
            return False
    
    def validate(self) -> List[str]:
        """Validate all configuration settings.
        
        Returns:
            List of error messages (empty if all valid)
        """
        errors = []
        errors.extend(self.can_settings.validate())
        errors.extend(self.ui_settings.validate())
        errors.extend(self.app_settings.validate())
        return errors
    
    # QSettings methods for user preferences (window position, recent files, etc.)
    
    def save_window_geometry(self, geometry: bytes) -> None:
        """Save window geometry to QSettings."""
        self._qsettings.setValue('window_geometry', geometry)
    
    def restore_window_geometry(self) -> Optional[bytes]:
        """Restore window geometry from QSettings."""
        return self._qsettings.value('window_geometry')
    
    def save_recent_files(self, files: List[str], max_count: int = 10) -> None:
        """Save recent files list to QSettings."""
        self._qsettings.setValue('recent_files', files[:max_count])
    
    def get_recent_files(self) -> List[str]:
        """Get recent files list from QSettings."""
        return self._qsettings.value('recent_files', [], type=list)
    
    def save_user_preference(self, key: str, value: Any) -> None:
        """Save a user preference to QSettings.
        
        Args:
            key: Preference key
            value: Preference value (must be JSON serializable)
        """
        self._qsettings.setValue(key, value)
    
    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference from QSettings.
        
        Args:
            key: Preference key
            default: Default value if preference not found
            
        Returns:
            Preference value or default
        """
        return self._qsettings.value(key, default)

