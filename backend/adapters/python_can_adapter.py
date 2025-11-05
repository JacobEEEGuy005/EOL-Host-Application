from __future__ import annotations
import threading
import time
from typing import Optional, Iterable

try:
    import can
except Exception:
    can = None
import logging
logger = logging.getLogger(__name__)

from .interface import Adapter, Frame


class PythonCanAdapter:
    """Wrapper around python-can Bus that implements the project's Adapter protocol.

    The adapter accepts and returns `backend.adapters.interface.Frame` objects so it
    can be used by the existing GUI and test runner without changes.
    """

    def __init__(self, channel: str = 'virtual', bitrate: Optional[int] = None, interface: Optional[str] = None):
        self.channel = channel
        self.bitrate = bitrate
        self.interface = interface
        self._bus: Optional[object] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._out_queue: list[Frame] = []
        self._lock = threading.Lock()
        
        # Validate Canalystii-specific parameters
        if interface == 'canalystii':
            if channel not in ('0', '1', 0, 1):
                raise ValueError(f"Invalid Canalystii channel: {channel}. Must be '0' or '1'")
            # Normalize channel to string for consistency
            if isinstance(channel, int):
                self.channel = str(channel)
            # Validate bitrate if provided (Canalyst-II supports: 10k, 20k, 50k, 125k, 250k, 500k, 800k, 1000k bps)
            if bitrate is not None:
                valid_bitrates = [10000, 20000, 50000, 125000, 250000, 500000, 800000, 1000000]
                if bitrate not in valid_bitrates:
                    logger.warning(f"Uncommon bitrate for Canalystii: {bitrate} bps. "
                                 f"Common values: {', '.join(str(b) for b in valid_bitrates)} bps")

    def open(self) -> None:
        if can is None:
            raise RuntimeError('python-can library not available')
        
        # Check if canalystii package is available when using canalystii interface
        if self.interface == 'canalystii':
            try:
                import canalystii
            except ImportError:
                raise RuntimeError('Canalystii adapter requires the "canalystii" package. '
                                'Install it with: pip install canalystii')
            logger.debug(f"Opening Canalystii adapter: channel={self.channel}, bitrate={self.bitrate} bps")
        
        kwargs = {}
        if self.bitrate is not None:
            try:
                kwargs['bitrate'] = int(self.bitrate)
            except Exception:
                pass
        # interface may be None for python-can to auto-select default backends
        if self.interface:
            try:
                self._bus = can.Bus(channel=self.channel, interface=self.interface, **kwargs)
                logger.debug(f"Successfully opened python-can Bus: interface={self.interface}, channel={self.channel}")
            except Exception as e:
                if self.interface == 'canalystii':
                    raise RuntimeError(f'Failed to open Canalystii adapter: {e}. '
                                     'Ensure the Canalyst-II device is connected and drivers are installed.') from e
                raise
        else:
            self._bus = can.Bus(channel=self.channel, **kwargs)

        # Re-apply any pending filters that were set before the bus was opened
        try:
            if getattr(self, '_pending_filters', None) is not None:
                self.set_filters(self._pending_filters)
                self._pending_filters = None
        except Exception:
            pass

        self._stop.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def _recv_loop(self) -> None:
        """Background thread: read from python-can bus and append to internal queue."""
        while not self._stop.is_set():
            try:
                msg = self._bus.recv(timeout=0.5) if self._bus is not None else None
                if msg is None:
                    continue
                f = Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b''), timestamp=getattr(msg, 'timestamp', time.time()))
                with self._lock:
                    self._out_queue.append(f)
            except Exception:
                time.sleep(0.1)
                continue

    def close(self) -> None:
        self._stop.set()
        if self._recv_thread:
            self._recv_thread.join(timeout=1.0)
        if self._bus is not None:
            try:
                # python-can API provides shutdown()
                self._bus.shutdown()
            except Exception:
                try:
                    self._bus.stop()
                except Exception:
                    pass
            self._bus = None

    def send(self, frame: Frame) -> None:
        if self._bus is None:
            raise RuntimeError('Bus not open')
        # build can.Message
        try:
            # Ensure classic CAN DLC of 8 bytes by padding with zeros if needed
            data_bytes = bytes(frame.data) if frame.data is not None else b''
            if len(data_bytes) < 8:
                data_bytes = data_bytes + b'\x00' * (8 - len(data_bytes))
            msg = can.Message(arbitration_id=int(frame.can_id), data=data_bytes, is_extended_id=False)
            self._bus.send(msg)
        except Exception:
            # best-effort: ignore send errors here and allow caller to handle
            raise

    def set_filters(self, filters) -> None:
        """Apply CAN filters to the underlying python-can Bus.

        `filters` is expected to be a list of dict-like entries containing at
        least 'can_id' and optionally 'can_mask' and 'extended'. This method
        will translate into the python-can expected filter dicts and call
        Bus.set_filters() when possible. If the Bus doesn't support filters
        this is a no-op.
        """
        if self._bus is None:
            # store filters locally so future open could reapply if desired
            self._pending_filters = list(filters) if filters is not None else None
            return
        try:
            can_filters = []
            if filters is None:
                can_filters = None
            else:
                for f in filters:
                    if isinstance(f, dict):
                        fid = int(f.get('can_id', 0))
                        extended = bool(f.get('extended', False))
                        # choose a sensible default mask
                        mask = int(f.get('can_mask')) if f.get('can_mask') is not None else (0x1FFFFFFF if extended else 0x7FF)
                        can_filters.append({'can_id': fid, 'can_mask': mask, 'extended': extended})
                    else:
                        # assume numeric id
                        try:
                            fid = int(f)
                        except Exception:
                            continue
                        can_filters.append({'can_id': fid, 'can_mask': 0x7FF, 'extended': False})
            # python-can accepts None to clear filters
            try:
                logger.info('Applying python-can filters: %s', can_filters)
                self._bus.set_filters(can_filters)
            except Exception:
                # some backends may not support set_filters; ignore
                logger.exception('Failed to apply python-can filters')
        except Exception:
            pass

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        if self._bus is None:
            return None
        try:
            msg = self._bus.recv(timeout=timeout)
            if msg is None:
                return None
            return Frame(can_id=msg.arbitration_id, data=bytes(msg.data or b''), timestamp=getattr(msg, 'timestamp', time.time()))
        except Exception:
            return None

    def iter_recv(self) -> Iterable[Frame]:
        # Yield frames from internal queue (pop as they arrive)
        idx = 0
        while not self._stop.is_set():
            with self._lock:
                if idx < len(self._out_queue):
                    f = self._out_queue[idx]
                    idx += 1
                    yield f
                    continue
            time.sleep(0.05)
