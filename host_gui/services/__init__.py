"""
Service layer for EOL Host Application.

This package contains service classes that encapsulate business logic,
separating it from the GUI layer for better testability and reusability.

Services:
- CanService: CAN adapter management and frame transmission
- DbcService: DBC file loading, parsing, and message/signal lookup
- SignalService: Signal decoding, caching, and value retrieval
"""

from host_gui.services.can_service import CanService
from host_gui.services.dbc_service import DbcService
from host_gui.services.signal_service import SignalService

__all__ = ['CanService', 'DbcService', 'SignalService']

