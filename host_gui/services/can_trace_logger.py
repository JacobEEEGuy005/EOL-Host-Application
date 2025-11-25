"""
CAN Trace Logger Service for logging CAN frames during test execution.

This module provides a thread-safe CAN trace logger that captures all CAN frames
(RX and TX) and writes them to a trace file. The logger includes periodic flushing
to prevent data loss in case of GUI crashes.
"""
import os
import threading
import time
from datetime import datetime
from typing import Optional
from queue import Queue, Empty
from backend.adapters.interface import Frame
import logging

logger = logging.getLogger(__name__)


class CanTraceLogger:
    """Thread-safe CAN trace logger with periodic file flushing.
    
    This logger captures all CAN frames (both RX and TX) and writes them
    to a trace file. Frames are buffered and periodically flushed to disk
    to prevent data loss in case of crashes.
    
    Features:
    - Thread-safe logging using locks and queues
    - Periodic flushing (every 2 seconds) to prevent data loss
    - Non-blocking frame logging (drops frames if queue is full)
    - Human-readable ASCII format
    - Automatic file naming with DUT UID, date, and time
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        """Initialize the CAN trace logger.
        
        Args:
            log_dir: Directory for trace files (defaults to backend/data/can_traces/)
        """
        # Determine log directory
        if log_dir is None:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
            log_dir = os.path.join(repo_root, 'backend', 'data', 'can_traces')
        
        os.makedirs(log_dir, exist_ok=True)
        self.log_dir = log_dir
        
        # Logging state
        self._is_logging = False
        self._log_file = None
        self._log_file_path = None
        self._frame_queue = Queue(maxsize=10000)  # Thread-safe queue for frames (limit to prevent memory issues)
        # Use RLock to allow nested acquisitions (e.g., stop -> flush -> stats update)
        self._lock = threading.RLock()
        
        # Flush thread
        self._flush_thread = None
        self._stop_flush = threading.Event()
        self._flush_interval = 2.0  # Flush every 2 seconds
        
        # Statistics
        self._frames_logged = 0
        self._frames_dropped = 0
    
    def start_logging(self, dut_uid: Optional[str] = None, test_name: Optional[str] = None) -> str:
        """Start logging CAN frames to a new trace file.
        
        The filename format is: {DUT_UID}_{YYYYMMDD}_{HHMMSS}.log
        If DUT_UID is not provided, uses "Unknown" as prefix.
        
        Args:
            dut_uid: DUT UID for filename (required for proper naming)
            test_name: Optional test name for header (not used in filename)
            
        Returns:
            Path to the log file
            
        Raises:
            RuntimeError: If logging is already active
            IOError: If file cannot be created
        """
        with self._lock:
            if self._is_logging:
                logger.warning("CAN trace logging already active, stopping previous session")
                self.stop_logging()
            
            # Generate filename: DUT_UID_YYYYMMDD_HHMMSS.log
            timestamp = datetime.now()
            date_str = timestamp.strftime('%Y%m%d')
            time_str = timestamp.strftime('%H%M%S')
            
            # Sanitize DUT UID for filename (remove invalid characters)
            if dut_uid:
                # Replace invalid filename characters with hyphen while preserving allowed ones
                safe_uid = "".join(
                    c if (c.isalnum() or c in ('-', '_', '.')) else '-'
                    for c in dut_uid
                ).strip('-_.')
                if not safe_uid:
                    safe_uid = "Unknown"
            else:
                safe_uid = "Unknown"
            
            filename = f"{safe_uid}_{date_str}_{time_str}.log"
            self._log_file_path = os.path.join(self.log_dir, filename)
            
            try:
                # Open file in append mode (safer for crashes)
                self._log_file = open(self._log_file_path, 'a', encoding='utf-8')
                
                # Write header
                header_lines = [
                    f"# CAN Trace Log",
                    f"# Started: {timestamp.isoformat()}",
                    f"# DUT UID: {dut_uid or 'N/A'}",
                    f"# Test: {test_name or 'N/A'}",
                    f"# Format: timestamp can_id direction data_hex",
                    f"#",
                ]
                self._log_file.write('\n'.join(header_lines) + '\n')
                self._log_file.flush()  # Immediate flush of header
                
                self._is_logging = True
                self._frames_logged = 0
                self._frames_dropped = 0
                
                # Start flush thread
                self._stop_flush.clear()
                self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
                self._flush_thread.start()
                
                logger.info(f"CAN trace logging started: {os.path.basename(self._log_file_path)}")
                return self._log_file_path
                
            except Exception as e:
                logger.error(f"Failed to start CAN trace logging: {e}", exc_info=True)
                if self._log_file:
                    try:
                        self._log_file.close()
                    except Exception:
                        pass
                    self._log_file = None
                raise RuntimeError(f"Failed to start CAN trace logging: {e}") from e
    
    def stop_logging(self) -> Optional[str]:
        """Stop logging and close the trace file.
        
        This method is designed to be non-blocking to avoid freezing the GUI.
        It processes frames in batches with time limits to ensure responsiveness.
        
        Returns:
            Path to the log file, or None if not logging
        """
        with self._lock:
            if not self._is_logging:
                return None
            # Capture thread and signal stop outside lock
            flush_thread = self._flush_thread
            self._flush_thread = None
            self._stop_flush.set()
        
        # Stop flush thread (non-blocking - use short timeout)
        if flush_thread:
            flush_thread.join(timeout=0.5)  # Reduced from 3.0 to 0.5 seconds
            if flush_thread.is_alive():
                logger.warning("Flush thread did not stop within timeout, continuing anyway")
        
        # Flush any remaining frames in batches with time limit (outside lock)
        max_flush_time = 0.5  # Maximum time to spend flushing (500ms)
        start_time = time.time()
        batch_size = 500  # Smaller batches
        
        while (time.time() - start_time) < max_flush_time:
            frames_written = self._flush_pending_frames_batch(batch_size)
            if frames_written == 0:
                break  # No more frames to process
        
        # Write footer and clean up state
        with self._lock:
            log_file = self._log_file
            log_path = self._log_file_path
            frames_logged = self._frames_logged
            frames_dropped = self._frames_dropped
            self._log_file = None
            self._log_file_path = None
            self._is_logging = False
        
        if log_file:
            try:
                footer_lines = [
                    f"#",
                    f"# CAN Trace Log Ended: {datetime.now().isoformat()}",
                    f"# Total Frames Logged: {frames_logged}",
                    f"# Frames Dropped: {frames_dropped}",
                ]
                log_file.write('\n'.join(footer_lines) + '\n')
                log_file.flush()
                log_file.close()
            except Exception as e:
                logger.error(f"Error closing CAN trace log file: {e}", exc_info=True)
        
        if log_path:
            logger.info(f"CAN trace logging stopped: {os.path.basename(log_path)} (logged {frames_logged} frames)")
        return log_path
    
    def _flush_pending_frames_batch(self, max_frames: int) -> int:
        """Flush a batch of pending frames from queue to file.
        
        Args:
            max_frames: Maximum number of frames to process in this batch
            
        Returns:
            Number of frames actually written
        """
        if not self._is_logging or not self._log_file:
            return 0
        
        frames_to_write = []
        
        # Drain queue (up to batch limit)
        try:
            for _ in range(max_frames):
                frame, direction, log_time = self._frame_queue.get_nowait()
                frames_to_write.append((frame, direction, log_time))
        except Empty:
            pass  # Queue empty, that's fine
        
        if not frames_to_write:
            return 0
        
        # Write frames to file
        try:
            lines = []
            for frame, direction, log_time in frames_to_write:
                # Format: timestamp can_id direction data_hex
                timestamp_str = datetime.fromtimestamp(log_time).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                can_id_hex = f"0x{frame.can_id:03X}"
                data_hex = ' '.join(f"{b:02X}" for b in frame.data) if frame.data else ""
                
                line = f"{timestamp_str} {can_id_hex} {direction} {data_hex}\n"
                lines.append(line)
            
            # Write all lines at once (more efficient)
            self._log_file.write(''.join(lines))
            self._log_file.flush()  # Force write to disk
            
            with self._lock:
                self._frames_logged += len(frames_to_write)
            
            return len(frames_to_write)
                
        except Exception as e:
            logger.error(f"Error writing CAN frames to trace file: {e}", exc_info=True)
            with self._lock:
                self._frames_dropped += len(frames_to_write)
            return len(frames_to_write)
    
    def log_frame(self, frame: Frame, direction: str = 'RX') -> None:
        """Log a CAN frame (thread-safe, non-blocking).
        
        Args:
            frame: CAN frame to log
            direction: 'RX' for received, 'TX' for transmitted
        """
        if not self._is_logging:
            return
        
        try:
            # Non-blocking put - drop frame if queue is full (prevents blocking)
            self._frame_queue.put_nowait((frame, direction, time.time()))
        except Exception:
            # Queue full - drop frame (better than blocking)
            with self._lock:
                self._frames_dropped += 1
    
    def _flush_loop(self) -> None:
        """Background thread that periodically flushes buffered frames to disk."""
        while not self._stop_flush.is_set():
            try:
                # Wait for flush interval or stop signal
                if self._stop_flush.wait(timeout=self._flush_interval):
                    break  # Stop signal received
                
                # Flush pending frames (process in batches)
                self._flush_pending_frames()
                
            except Exception as e:
                logger.error(f"Error in CAN trace flush loop: {e}", exc_info=True)
    
    def _flush_pending_frames(self) -> None:
        """Flush all pending frames from queue to file (called from flush thread).
        
        This method processes frames in batches to avoid blocking.
        """
        if not self._is_logging or not self._log_file:
            return
        
        # Process frames in batches until queue is empty or batch limit reached
        batch_size = 1000
        max_batches = 10  # Limit number of batches per flush cycle
        
        for _ in range(max_batches):
            frames_written = self._flush_pending_frames_batch(batch_size)
            if frames_written == 0:
                break  # No more frames to process
    
    def is_logging(self) -> bool:
        """Check if logging is currently active."""
        with self._lock:
            return self._is_logging
    
    def get_log_path(self) -> Optional[str]:
        """Get path to current log file."""
        with self._lock:
            return self._log_file_path

