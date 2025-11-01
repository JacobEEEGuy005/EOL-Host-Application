"""
Data models for EOL Host Application.

This package contains data models and value objects used throughout
the application for type safety and data validation.

Models:
- CanFrame: Represents a CAN bus frame
- SignalValue: Represents a decoded signal value with metadata
- TestProfile: Test configuration model
"""

from host_gui.models.can_frame import CanFrame
from host_gui.models.signal_value import SignalValue
from host_gui.models.test_profile import TestProfile

__all__ = ['CanFrame', 'SignalValue', 'TestProfile']

