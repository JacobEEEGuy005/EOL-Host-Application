"""
CAN Service for managing CAN bus adapters and frame transmission.

This service encapsulates all CAN adapter management logic, providing
a clean interface for connecting to adapters, sending frames, and
receiving frames via background worker threads.
"""
import os
import queue
import threading
import logging
from typing import Optional, Dict, Any, List
from backend.adapters.interface import Frame, Adapter

logger = logging.getLogger(__name__)

# Import adapters (handle optional imports gracefully)
try:
    from backend.adapters.sim import SimAdapter
except Exception:
    SimAdapter = None

try:
    from backend.adapters.pcan import PcanAdapter
except Exception:
    PcanAdapter = None

try:
    from backend.adapters.python_can_adapter import PythonCanAdapter
except Exception:
    PythonCanAdapter = None

from host_gui.constants import CAN_CHANNEL_DEFAULT, CAN_BITRATE_DEFAULT


class AdapterWorker(threading.Thread):
    """Background worker thread that receives CAN frames from adapter and enqueues them.
    
    This worker runs in a separate thread to prevent blocking the GUI main thread.
    Frames received from the adapter are placed into a queue for processing by the
    GUI's frame polling mechanism.
    
    Attributes:
        adapter: CAN adapter instance (must implement iter_recv() method)
        out_q: Queue for outgoing frames to GUI
        _stop: Event to signal thread shutdown
    """
    
    def __init__(self, adapter: Adapter, out_q: queue.Queue):
        """Initialize the adapter worker thread.
        
        Args:
            adapter: CAN adapter instance (SimAdapter, PcanAdapter, etc.)
            out_q: Queue.Queue for frames to be processed by GUI
        """
        super().__init__(daemon=True)
        self.adapter = adapter
        self.out_q = out_q
        self._stop = threading.Event()

    def run(self):
        """Main thread loop: continuously receive frames and enqueue them."""
        try:
            for frame in self.adapter.iter_recv():
                if self._stop.is_set():
                    logger.debug("AdapterWorker: stop signal received")
                    break
                self.out_q.put(frame)
        except Exception as e:
            logger.error(f"AdapterWorker error in run loop: {e}", exc_info=True)

    def stop(self):
        """Signal the worker thread to stop. Thread will exit after current frame."""
        self._stop.set()
        logger.debug("AdapterWorker: stop() called")


class CanService:
    """Service for managing CAN bus adapters and frame operations.
    
    This service provides a high-level interface for:
    - Connecting/disconnecting CAN adapters
    - Sending CAN frames
    - Receiving frames via background worker thread
    - Managing adapter-specific configuration (channel, bitrate)
    
    Attributes:
        adapter: Current CAN adapter instance (None when disconnected)
        worker: Background worker thread for frame reception
        frame_queue: Queue for frames received by worker
        adapter_name: Name of currently connected adapter ('Sim', 'PCAN', etc.)
        channel: CAN channel/interface identifier
        bitrate: CAN bitrate in kbps
    """
    
    def __init__(self, channel: Optional[str] = None, bitrate: Optional[int] = None):
        """Initialize the CAN service.
        
        Args:
            channel: CAN channel/interface (defaults to CAN_CHANNEL_DEFAULT or env var)
            bitrate: CAN bitrate in kbps (defaults to CAN_BITRATE_DEFAULT or env var)
        """
        self.adapter: Optional[Adapter] = None
        self.worker: Optional[AdapterWorker] = None
        self.frame_queue = queue.Queue()
        self.adapter_name: Optional[str] = None
        
        # Load channel and bitrate from environment or use defaults
        self.channel = channel or os.environ.get('CAN_CHANNEL', os.environ.get('PCAN_CHANNEL', CAN_CHANNEL_DEFAULT))
        try:
            self.bitrate = bitrate or int(os.environ.get('CAN_BITRATE', os.environ.get('PCAN_BITRATE', str(CAN_BITRATE_DEFAULT))))
        except (ValueError, TypeError):
            self.bitrate = CAN_BITRATE_DEFAULT
    
    def connect(self, adapter_type: str) -> bool:
        """Connect to a CAN adapter of the specified type.
        
        Args:
            adapter_type: Type of adapter ('SimAdapter', 'PCAN', 'PythonCAN', 'Canalystii', 'SocketCAN')
            
        Returns:
            True if connection successful, False otherwise
            
        Raises:
            ValueError: If adapter_type is not supported
            RuntimeError: If adapter initialization fails
        """
        if self.is_connected():
            logger.warning("Attempted to connect when adapter already connected")
            return False
        
        logger.info(f"Connecting to adapter type: {adapter_type}")
        
        # Try to instantiate the selected adapter
        if adapter_type == 'SimAdapter':
            if SimAdapter is None:
                raise RuntimeError("SimAdapter not available")
            try:
                self.adapter = SimAdapter()
                self.adapter.open()
                self.adapter_name = 'Sim'
            except Exception as e:
                logger.error(f"Failed to open SimAdapter: {e}", exc_info=True)
                raise RuntimeError(f"Failed to open SimAdapter: {e}")
        
        elif adapter_type == 'PCAN':
            if PcanAdapter is None:
                raise ValueError("PCAN adapter not available (PCAN drivers may not be installed)")
            try:
                br = self.bitrate if self.bitrate else None
                self.adapter = PcanAdapter(channel=self.channel, bitrate=br)
                self.adapter.open()
                self.adapter_name = 'PCAN'
            except Exception as e:
                logger.error(f"Failed to open PCAN adapter: {e}", exc_info=True)
                raise RuntimeError(f"Failed to open PCAN adapter: {e}")
        
        elif adapter_type in ('PythonCAN', 'Canalystii'):
            if PythonCanAdapter is None:
                raise ValueError("PythonCAN adapter not available (python-can may not be installed)")
            try:
                # PythonCAN and Canalystii both use PythonCanAdapter with different interfaces
                interface_name = 'canalystii' if adapter_type == 'Canalystii' else None
                br = self.bitrate
                # Canalystii expects bitrate in bps, convert from kbps
                if adapter_type == 'Canalystii' and br is not None:
                    br = br * 1000
                self.adapter = PythonCanAdapter(channel=self.channel, bitrate=br, interface=interface_name)
                self.adapter.open()
                self.adapter_name = adapter_type
            except Exception as e:
                logger.error(f"Failed to open {adapter_type} adapter: {e}", exc_info=True)
                raise RuntimeError(f"Failed to open {adapter_type} adapter: {e}")
        
        elif adapter_type == 'SocketCAN':
            if PythonCanAdapter is None:
                raise ValueError("SocketCAN adapter not available (python-can may not be installed)")
            try:
                self.adapter = PythonCanAdapter(channel=self.channel, bitrate=self.bitrate, interface='socketcan')
                self.adapter.open()
                self.adapter_name = 'SocketCAN'
            except Exception as e:
                logger.error(f"Failed to open SocketCAN adapter: {e}", exc_info=True)
                raise RuntimeError(f"Failed to open SocketCAN adapter: {e}")
        
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")
        
        # Start background worker for frame reception
        self.worker = AdapterWorker(self.adapter, self.frame_queue)
        self.worker.start()
        logger.info(f"Successfully connected to {self.adapter_name} adapter")
        return True
    
    def disconnect(self):
        """Disconnect from the current adapter and clean up resources."""
        if not self.is_connected():
            logger.debug("Attempted to disconnect when no adapter connected")
            return
        
        logger.info("Disconnecting adapter...")
        
        # Stop worker thread
        if self.worker:
            try:
                self.worker.stop()
                logger.debug("Stopped AdapterWorker")
            except Exception as e:
                logger.warning(f"Error stopping AdapterWorker: {e}")
            self.worker = None
        
        # Close adapter
        if self.adapter:
            try:
                self.adapter.close()
                logger.info("Closed adapter")
            except Exception as e:
                logger.warning(f"Error closing adapter: {e}", exc_info=True)
            self.adapter = None
        
        self.adapter_name = None
        logger.info("Adapter disconnected and cleaned up")
    
    def is_connected(self) -> bool:
        """Check if an adapter is currently connected.
        
        Returns:
            True if adapter is connected, False otherwise
        """
        return self.adapter is not None
    
    def send_frame(self, frame: Frame) -> bool:
        """Send a CAN frame through the connected adapter.
        
        Args:
            frame: CAN frame to send (with can_id, data, optional timestamp)
            
        Returns:
            True if frame sent successfully, False otherwise
            
        Raises:
            RuntimeError: If no adapter is connected
        """
        if not self.is_connected():
            raise RuntimeError("Cannot send frame: no adapter connected")
        
        try:
            self.adapter.send(frame)
            logger.debug(f"Sent frame: can_id=0x{frame.can_id:X} data={frame.data.hex()}")
            return True
        except Exception as e:
            logger.error(f"Failed to send frame: {e}", exc_info=True)
            return False
    
    def get_frame(self, timeout: Optional[float] = None) -> Optional[Frame]:
        """Get a frame from the frame queue (non-blocking or with timeout).
        
        Args:
            timeout: Optional timeout in seconds (None = non-blocking)
            
        Returns:
            Frame if available, None if timeout or queue empty
        """
        try:
            if timeout is None:
                return self.frame_queue.get_nowait()
            else:
                return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_available_adapters(self) -> List[str]:
        """Get list of available adapter types based on installed drivers.
        
        Returns:
            List of adapter type names that are available
        """
        adapters = []
        
        # SimAdapter is always available
        adapters.append('SimAdapter')
        
        # Check for PCAN
        if PcanAdapter is not None:
            adapters.append('PCAN')
        
        # Check for PythonCAN (supports multiple interfaces)
        if PythonCanAdapter is not None:
            adapters.append('PythonCAN')
            adapters.append('Canalystii')
            # SocketCAN is also via PythonCAN on Linux
            import sys
            if sys.platform.startswith('linux'):
                adapters.append('SocketCAN')
        
        return adapters
    
    def set_filters(self, filters: List[Dict[str, Any]]) -> bool:
        """Set CAN frame filters on the adapter (if supported).
        
        Args:
            filters: List of filter dictionaries with 'can_id' and 'extended' keys
            
        Returns:
            True if filters set successfully, False otherwise
        """
        if not self.is_connected():
            logger.warning("Cannot set filters: no adapter connected")
            return False
        
        if not hasattr(self.adapter, 'set_filters'):
            logger.debug("Adapter does not support filters")
            return False
        
        try:
            self.adapter.set_filters(filters)
            logger.debug(f"Set {len(filters)} filters on adapter")
            return True
        except Exception as e:
            logger.warning(f"Failed to set filters: {e}")
            return False
    
    def set_channel(self, channel: str):
        """Update CAN channel setting (takes effect on next connect).
        
        Args:
            channel: CAN channel/interface identifier
        """
        self.channel = channel
        logger.debug(f"CAN channel set to: {channel}")
    
    def set_bitrate(self, bitrate: int):
        """Update CAN bitrate setting in kbps (takes effect on next connect).
        
        Args:
            bitrate: CAN bitrate in kbps
        """
        self.bitrate = bitrate
        logger.debug(f"CAN bitrate set to: {bitrate} kbps")

