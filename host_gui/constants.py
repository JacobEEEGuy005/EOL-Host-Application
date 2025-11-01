"""
Constants and configuration values for the EOL Host GUI application.

This module centralizes all magic numbers, limits, and configuration values
used throughout the GUI application. This improves maintainability by
providing a single source of truth for these values.

Constants are organized by category:
- CAN ID ranges and limits
- DAC voltage specifications
- CAN frame specifications
- Timing constants (dwell times, poll intervals)
- Display limits
- Message Type values from DBC specification
- Default CAN bus settings

All values are based on the EOL hardware and IPC specifications defined in
the DBC file (docs/can_specs/eol_firmware.dbc).
"""

# CAN ID ranges
CAN_ID_MIN = 0
CAN_ID_MAX_STANDARD = 0x7FF  # Standard CAN (11-bit)
CAN_ID_MAX_EXTENDED = 0x1FFFFFFF  # Extended CAN (29-bit)
CAN_ID_MAX = CAN_ID_MAX_EXTENDED  # Use extended as maximum

# DAC voltage limits (millivolts)
DAC_VOLTAGE_MIN = 0
DAC_VOLTAGE_MAX = 5000  # 5V = 5000mV

# CAN frame limits
CAN_FRAME_MAX_LENGTH = 8  # Classic CAN maximum data length

# Timing constants (milliseconds)
DWELL_TIME_DEFAULT = 100
DWELL_TIME_MIN = 100
POLL_INTERVAL_MS = 50  # 0.05 seconds
FRAME_POLL_INTERVAL_MS = 150

# Display limits
MAX_MESSAGES_DEFAULT = 50
MAX_FRAMES_DEFAULT = 50

# Message Type values from DBC (Command message CAN ID 272)
MSG_TYPE_SET_RELAY = 16
MSG_TYPE_SET_MUX = 17
MSG_TYPE_SET_DAC = 18
MSG_TYPE_REQ_IPC_DATA = 19

# Feedback Message Types (IPC Status CAN ID 250)
MSG_TYPE_DIG_SIG1 = 100
MSG_TYPE_ANALOG_VALUES1 = 101
MSG_TYPE_ANALOG_VALUES2 = 102
MSG_TYPE_ANALOG_VALUES3 = 103
MSG_TYPE_ANALOG_VALUES4 = 104

# CAN IDs from DBC
CAN_ID_COMMAND = 0x110  # 272
CAN_ID_IPC_STATUS = 0xFA  # 250
CAN_ID_EOL_STATUS = 0x100  # 256

# Default CAN settings
CAN_BITRATE_DEFAULT = 500  # kbps
CAN_CHANNEL_DEFAULT = '0'

