"""
DBC Service for managing DBC (Database CAN) files and operations.

This service encapsulates DBC file loading, parsing, message/signal lookup,
and encoding/decoding operations using the cantools library.
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Import cantools (handle optional import)
try:
    import cantools
    CANTOOLS_AVAILABLE = True
except ImportError:
    cantools = None
    CANTOOLS_AVAILABLE = False

# Determine repo root for default paths
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


class DbcService:
    """Service for managing DBC files and operations.
    
    This service provides:
    - Loading and parsing DBC files
    - Finding messages by CAN ID
    - Finding signals within messages
    - Encoding/decoding signals
    - Managing DBC file index/persistence
    
    Attributes:
        database: Loaded cantools database object (None if no DBC loaded)
        dbc_path: Path to currently loaded DBC file
        _message_cache: Cache mapping CAN ID -> message object
        _signal_lookup_cache: Cache mapping "can_id:signal_name" -> (message, signal)
    """
    
    def __init__(self):
        """Initialize the DBC service."""
        self.database: Optional[Any] = None  # cantools.Database object
        self.dbc_path: Optional[str] = None
        self._message_cache: Dict[int, Any] = {}
        self._signal_lookup_cache: Dict[str, Tuple[Any, Any]] = {}
    
    def load_dbc_file(self, filepath: str) -> bool:
        """Load and parse a DBC file.
        
        Args:
            filepath: Path to DBC file
            
        Returns:
            True if loaded successfully, False otherwise
            
        Raises:
            RuntimeError: If cantools is not available
            FileNotFoundError: If DBC file does not exist
            ValueError: If DBC file cannot be parsed
        """
        if not CANTOOLS_AVAILABLE:
            raise RuntimeError("cantools library is not available. Install cantools to use DBC functionality.")
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"DBC file not found: {filepath}")
        
        logger.info(f"Loading DBC file: {filepath}")
        
        try:
            # Try newer API first, fallback to older
            try:
                db = cantools.database.load_file(filepath)
            except AttributeError:
                db = cantools.db.load_file(filepath)
            
            self.database = db
            self.dbc_path = filepath
            
            # Clear caches when new DBC is loaded
            self.clear_caches()
            
            message_count = len(getattr(db, 'messages', []))
            logger.info(f"DBC loaded successfully: {message_count} messages")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load DBC file {filepath}: {e}", exc_info=True)
            self.database = None
            self.dbc_path = None
            raise ValueError(f"Failed to parse DBC file: {e}")
    
    def is_loaded(self) -> bool:
        """Check if a DBC file is currently loaded.
        
        Returns:
            True if DBC is loaded, False otherwise
        """
        return self.database is not None
    
    def find_message_by_id(self, can_id: int) -> Optional[Any]:
        """Find a message by its CAN ID.
        
        Args:
            can_id: CAN identifier (0-0x1FFFFFFF)
            
        Returns:
            Message object from cantools database, or None if not found
            
        Uses caching for performance.
        """
        if not self.is_loaded():
            return None
        
        # Check cache first
        if can_id in self._message_cache:
            cached = self._message_cache[can_id]
            if cached is None:
                return None
            return cached
        
        # Search for message
        for msg in getattr(self.database, 'messages', []):
            msg_id = getattr(msg, 'frame_id', getattr(msg, 'arbitration_id', None))
            if msg_id is not None and int(msg_id) == int(can_id):
                self._message_cache[can_id] = msg
                return msg
        
        # Cache None to avoid repeated searches
        self._message_cache[can_id] = None
        return None
    
    def find_message_and_signal(self, can_id: int, signal_name: str) -> Tuple[Optional[Any], Optional[Any]]:
        """Find both message and signal by CAN ID and signal name.
        
        Args:
            can_id: CAN identifier
            signal_name: Name of the signal to find
            
        Returns:
            Tuple of (message, signal) or (None, None) if not found
            
        Uses caching for performance.
        """
        if not self.is_loaded():
            return (None, None)
        
        # Check cache first
        key = f"{can_id}:{signal_name}"
        if key in self._signal_lookup_cache:
            return self._signal_lookup_cache[key]
        
        # Find message
        msg = self.find_message_by_id(can_id)
        if msg is None:
            self._signal_lookup_cache[key] = (None, None)
            return (None, None)
        
        # Find signal in message
        for sig in getattr(msg, 'signals', []):
            if sig.name == signal_name:
                result = (msg, sig)
                self._signal_lookup_cache[key] = result
                return result
        
        # Signal not found
        self._signal_lookup_cache[key] = (None, None)
        return (None, None)
    
    def get_all_messages(self) -> List[Any]:
        """Get all messages from the loaded DBC.
        
        Returns:
            List of message objects, or empty list if no DBC loaded
        """
        if not self.is_loaded():
            return []
        return list(getattr(self.database, 'messages', []))
    
    def get_message_signals(self, message: Any) -> List[Any]:
        """Get all signals from a message.
        
        Args:
            message: Message object from cantools
            
        Returns:
            List of signal objects
        """
        if message is None:
            return []
        return list(getattr(message, 'signals', []))
    
    def encode_message(self, message: Any, signals: Dict[str, Any]) -> bytes:
        """Encode signal values into a CAN frame using the message definition.
        
        Args:
            message: Message object from cantools database
            signals: Dictionary mapping signal names to values
            
        Returns:
            Encoded frame data as bytes
            
        Raises:
            ValueError: If encoding fails
        """
        if not self.is_loaded():
            raise RuntimeError("No DBC loaded")
        
        try:
            return message.encode(signals)
        except Exception as e:
            logger.error(f"Failed to encode message: {e}", exc_info=True)
            raise ValueError(f"Encoding failed: {e}")
    
    def decode_message(self, message: Any, data: bytes) -> Dict[str, Any]:
        """Decode a CAN frame into signal values using the message definition.
        
        Args:
            message: Message object from cantools database
            data: CAN frame data bytes
            
        Returns:
            Dictionary mapping signal names to decoded values
            
        Raises:
            ValueError: If decoding fails
        """
        if not self.is_loaded():
            raise RuntimeError("No DBC loaded")
        
        try:
            return message.decode(data)
        except Exception as e:
            logger.error(f"Failed to decode message: {e}", exc_info=True)
            raise ValueError(f"Decoding failed: {e}")
    
    def clear_caches(self):
        """Clear all caches (call when DBC is reloaded)."""
        self._message_cache.clear()
        self._signal_lookup_cache.clear()
        logger.debug("Cleared DBC lookup caches")
    
    def save_dbc_to_index(self, filepath: str, original_name: Optional[str] = None) -> bool:
        """Save a DBC file reference to the index for persistence.
        
        Args:
            filepath: Path to DBC file (will be copied to data directory)
            original_name: Original filename (if different from filepath basename)
            
        Returns:
            True if saved successfully, False otherwise
        """
        dbc_dir = os.path.join(repo_root, 'backend', 'data', 'dbcs')
        os.makedirs(dbc_dir, exist_ok=True)
        
        base = os.path.basename(filepath)
        original = original_name or base
        
        # Ensure unique filename
        dest = os.path.join(dbc_dir, base)
        i = 1
        while os.path.exists(dest):
            name, ext = os.path.splitext(base)
            dest = os.path.join(dbc_dir, f"{name}-{i}{ext}")
            i += 1
        
        try:
            import shutil
            shutil.copyfile(filepath, dest)
            
            # Update index.json
            index_path = os.path.join(dbc_dir, 'index.json')
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    idx = json.load(f)
            else:
                idx = {'dbcs': []}
            
            idx['dbcs'].append({
                'filename': os.path.basename(dest),
                'original_name': original,
                'uploaded_at': datetime.utcnow().isoformat() + 'Z'
            })
            
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(idx, f, indent=2)
            
            logger.info(f"Saved DBC to index: {original} -> {os.path.basename(dest)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save DBC to index: {e}", exc_info=True)
            return False
    
    def get_indexed_dbcs(self) -> List[Dict[str, str]]:
        """Get list of DBC files from the index.
        
        Returns:
            List of dictionaries with 'filename' and 'original_name' keys
        """
        index_path = os.path.join(repo_root, 'backend', 'data', 'dbcs', 'index.json')
        if not os.path.exists(index_path):
            return []
        
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('dbcs', [])
        except Exception as e:
            logger.warning(f"Failed to read DBC index: {e}")
            return []
    
    def get_dbc_path_from_index(self, filename: str) -> Optional[str]:
        """Get full path to a DBC file from the index.
        
        Args:
            filename: Filename from index
            
        Returns:
            Full path to DBC file, or None if not found
        """
        dbc_dir = os.path.join(repo_root, 'backend', 'data', 'dbcs')
        filepath = os.path.join(dbc_dir, filename)
        if os.path.exists(filepath):
            return filepath
        return None

