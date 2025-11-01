"""
Service Container for Dependency Injection.

This module provides a centralized container for managing service instances
and their dependencies, implementing the Dependency Injection pattern to
reduce coupling and improve testability.
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Centralized container for managing service instances and dependencies.
    
    This container implements the Dependency Injection pattern, providing
    a single source of truth for service instances and managing their
    lifecycle. Services are initialized lazily and can be accessed by
    components that need them.
    
    Attributes:
        _services: Dictionary mapping service names to service instances
        _initialized: Set of service names that have been initialized
    """
    
    def __init__(self):
        """Initialize the service container."""
        self._services: Dict[str, Any] = {}
        self._initialized: set = set()
        logger.info("ServiceContainer initialized")
    
    def register(self, name: str, service: Any, lazy: bool = False) -> None:
        """Register a service with the container.
        
        Args:
            name: Name identifier for the service (e.g., 'can_service')
            service: Service instance or callable factory function
            lazy: If True, service is created lazily on first access
                  If False, service is stored as-is
        """
        if lazy and callable(service):
            # Store factory function for lazy initialization
            self._services[name] = ('factory', service)
        else:
            # Store service instance directly
            self._services[name] = ('instance', service)
            self._initialized.add(name)
        
        logger.debug(f"Registered service: {name} (lazy={lazy})")
    
    def get(self, name: str) -> Optional[Any]:
        """Get a service instance by name.
        
        Args:
            name: Name identifier for the service
            
        Returns:
            Service instance or None if not found
        """
        if name not in self._services:
            logger.warning(f"Service not found: {name}")
            return None
        
        service_type, service_value = self._services[name]
        
        if service_type == 'factory':
            # Lazy initialization
            if name not in self._initialized:
                try:
                    logger.debug(f"Lazy initializing service: {name}")
                    service_value = service_value()  # Call factory function
                    self._services[name] = ('instance', service_value)
                    self._initialized.add(name)
                except Exception as e:
                    logger.error(f"Failed to initialize service {name}: {e}", exc_info=True)
                    return None
            else:
                _, service_value = self._services[name]
        
        return service_value
    
    def has(self, name: str) -> bool:
        """Check if a service is registered.
        
        Args:
            name: Name identifier for the service
            
        Returns:
            True if service is registered, False otherwise
        """
        return name in self._services
    
    def remove(self, name: str) -> None:
        """Remove a service from the container.
        
        Args:
            name: Name identifier for the service
        """
        if name in self._services:
            # If service has cleanup method, call it
            service = self.get(name)
            if service is not None and hasattr(service, 'cleanup'):
                try:
                    service.cleanup()
                except Exception as e:
                    logger.warning(f"Error cleaning up service {name}: {e}", exc_info=True)
            
            del self._services[name]
            self._initialized.discard(name)
            logger.debug(f"Removed service: {name}")
    
    def clear(self) -> None:
        """Clear all services from the container and cleanup."""
        # Cleanup all services before clearing
        for name in list(self._services.keys()):
            self.remove(name)
        
        self._services.clear()
        self._initialized.clear()
        logger.info("ServiceContainer cleared")
    
    def initialize_services(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize core services with default configuration.
        
        This method creates and registers the core services used by the
        application: CanService, DbcService, and SignalService.
        
        Args:
            config: Optional configuration dictionary with service parameters:
                - can_channel: CAN channel/interface (defaults to env or default)
                - can_bitrate: CAN bitrate in kbps (defaults to env or default)
                - dbc_dir: Directory for DBC file storage (optional)
        """
        if config is None:
            config = {}
        
        # Import services (with graceful fallback)
        try:
            from host_gui.services.can_service import CanService
            from host_gui.services.dbc_service import DbcService
            from host_gui.services.signal_service import SignalService
            from host_gui.constants import CAN_CHANNEL_DEFAULT, CAN_BITRATE_DEFAULT
        except ImportError as e:
            logger.error(f"Failed to import services: {e}", exc_info=True)
            return
        
        # Register CanService
        if CanService is not None:
            can_channel = config.get('can_channel', CAN_CHANNEL_DEFAULT)
            can_bitrate = config.get('can_bitrate', CAN_BITRATE_DEFAULT)
            can_service = CanService(channel=can_channel, bitrate=can_bitrate)
            self.register('can_service', can_service)
            logger.info(f"Registered CanService with channel={can_channel}, bitrate={can_bitrate}kbps")
        
        # Register DbcService
        if DbcService is not None:
            # DbcService doesn't take dbc_dir parameter in constructor, uses default
            dbc_service = DbcService()
            self.register('dbc_service', dbc_service)
            logger.info("Registered DbcService with default configuration")
        
        # Register SignalService (depends on DbcService)
        if SignalService is not None:
            dbc_service = self.get('dbc_service')
            if dbc_service is not None:
                signal_service = SignalService(dbc_service)
                self.register('signal_service', signal_service)
                logger.info("Registered SignalService")
            else:
                logger.warning("Cannot register SignalService: DbcService not available")
    
    def get_can_service(self):
        """Convenience method to get CanService."""
        return self.get('can_service')
    
    def get_dbc_service(self):
        """Convenience method to get DbcService."""
        return self.get('dbc_service')
    
    def get_signal_service(self):
        """Convenience method to get SignalService."""
        return self.get('signal_service')
    
    def __repr__(self) -> str:
        """String representation of the container."""
        services = ', '.join(self._services.keys())
        return f"ServiceContainer(services=[{services}])"

