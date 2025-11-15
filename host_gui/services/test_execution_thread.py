"""
Test Execution Thread for running tests in background.

This module provides a QThread-based implementation for executing tests
asynchronously, preventing UI blocking during long-running test sequences.
"""
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from PySide6 import QtCore

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from host_gui.services.can_service import CanService
    from host_gui.services.dbc_service import DbcService
    from host_gui.services.signal_service import SignalService
from host_gui.constants import SLEEP_INTERVAL_SHORT

logger = logging.getLogger(__name__)


class TestExecutionThread(QtCore.QThread):
    """Background thread for executing test sequences without blocking the UI.
    
    This thread executes tests in sequence, emitting progress and result
    signals for GUI updates. The thread can be cancelled by calling stop().
    
    Signals:
        test_started: Emitted when a test starts (test_index, test_name)
        test_progress: Emitted during test execution (progress: 0.0-1.0)
        test_finished: Emitted when a test completes (test_index, success, info, exec_time)
        test_failed: Emitted when a test fails with exception (test_index, error)
        sequence_started: Emitted when sequence starts (total_tests)
        sequence_progress: Emitted for overall sequence progress (current, total)
        sequence_finished: Emitted when sequence completes (results, summary)
        sequence_cancelled: Emitted when sequence is cancelled
        sequence_paused: Emitted when sequence is paused
        sequence_resumed: Emitted when sequence is resumed
    """
    
    # Signals
    test_started = QtCore.Signal(int, str)  # test_index, test_name
    test_progress = QtCore.Signal(float)  # progress 0.0-1.0
    test_finished = QtCore.Signal(int, bool, str, float)  # test_index, success, info, exec_time
    test_failed = QtCore.Signal(int, str, float)  # test_index, error, exec_time
    sequence_started = QtCore.Signal(int)  # total_tests
    sequence_progress = QtCore.Signal(int, int)  # current, total
    sequence_finished = QtCore.Signal(list, str)  # results list, summary text
    sequence_cancelled = QtCore.Signal()
    sequence_paused = QtCore.Signal()  # Emitted when sequence is paused
    sequence_resumed = QtCore.Signal()  # Emitted when sequence is resumed
    
    def __init__(self, 
                 tests: List[Dict[str, Any]],
                 test_runner,
                 can_service: Optional['CanService'] = None,
                 dbc_service: Optional['DbcService'] = None,
                 signal_service: Optional['SignalService'] = None,
                 timeout: float = 1.0):
        """Initialize the test execution thread.
        
        Args:
            tests: List of test configuration dictionaries
            test_runner: TestRunner instance for executing tests
            can_service: CanService instance (optional)
            dbc_service: DbcService instance (optional)
            signal_service: SignalService instance (optional)
            timeout: Timeout per test in seconds
        """
        super().__init__()
        self.tests = tests
        self.test_runner = test_runner
        self.can_service = can_service
        self.dbc_service = dbc_service
        self.signal_service = signal_service
        self.timeout = timeout
        self._stop_requested = False
        self._pause_requested = False
        self._is_paused = False
        self._pause_lock = QtCore.QMutex()
        self._pause_condition = QtCore.QWaitCondition()
        self._current_test_index = -1
    
    def stop(self):
        """Request the thread to stop execution after current test completes."""
        self._stop_requested = True
        logger.info("Test execution thread stop requested")
    
    def pause(self):
        """Request the thread to pause after current test completes.
        
        The current test will finish, then the sequence will pause before
        starting the next test. Use resume() to continue.
        """
        if not self._is_paused:
            self._pause_requested = True
            logger.info("Test execution thread pause requested")
    
    def resume(self):
        """Resume the paused test sequence.
        
        The sequence will continue from the next test in the sequence.
        """
        if self._is_paused:
            self._pause_lock.lock()
            self._pause_requested = False
            self._is_paused = False
            self._pause_condition.wakeAll()
            self._pause_lock.unlock()
            logger.info("Test execution thread resumed")
    
    def is_paused(self) -> bool:
        """Check if thread is currently paused.
        
        Returns:
            True if thread is paused, False otherwise
        """
        return self._is_paused
    
    def run(self):
        """Execute all tests in sequence (runs in background thread)."""
        if not self.tests:
            logger.warning("TestExecutionThread.run() called but tests list is empty")
            return
        
        # Reset pause flags at start
        self._pause_requested = False
        self._is_paused = False
        
        total_tests = len(self.tests)
        logger.info(f"TestExecutionThread.run() starting with {total_tests} tests")
        self.sequence_started.emit(total_tests)
        
        results = []
        exec_times = []
        cancelled = False
        
        try:
            for i, test in enumerate(self.tests):
                if self._stop_requested:
                    logger.info(f"Test execution cancelled at test {i+1}/{total_tests}")
                    cancelled = True
                    break
                
                self._current_test_index = i
                test_name = test.get('name', '<unnamed>')
                
                # Emit test started signal
                self.test_started.emit(i, test_name)
                self.sequence_progress.emit(i, total_tests)
                
                logger.info(f"Executing test {i+1}/{total_tests}: {test_name}")
                
                start_time = time.time()
                try:
                    # Execute test (this may take time)
                    success, info = self.test_runner.run_single_test(test, self.timeout)
                    end_time = time.time()
                    exec_time = end_time - start_time
                    exec_times.append(exec_time)
                    
                    results.append((test_name, success, info))
                    
                    # Emit test finished signal
                    self.test_finished.emit(i, success, info, exec_time)
                    logger.info(f"Test {i+1} completed: {'PASS' if success else 'FAIL'}")
                    
                except Exception as e:
                    end_time = time.time()
                    exec_time = end_time - start_time
                    exec_times.append(exec_time)
                    
                    error_msg = str(e)
                    results.append((test_name, False, error_msg))
                    
                    # Emit test failed signal
                    self.test_failed.emit(i, error_msg, exec_time)
                    logger.error(f"Test {i+1} failed with exception: {e}", exc_info=True)
                
                # Emit progress update
                progress = (i + 1) / total_tests
                self.test_progress.emit(progress)
                
                # Check for pause request after test completes (but before next test starts)
                # Pause if requested and there are more tests to run, OR if this was the last test
                # (pausing on last test allows user to review results before sequence ends)
                if self._pause_requested:
                    if i < total_tests - 1:
                        # Pause before next test
                        self._pause_lock.lock()
                        self._is_paused = True
                        self.sequence_paused.emit()
                        logger.info(f"Test sequence paused after test {i+1}/{total_tests}")
                        
                        # Wait until resume is called
                        while self._is_paused and not self._stop_requested:
                            self._pause_condition.wait(self._pause_lock, 100)  # Wait 100ms at a time
                        
                        if not self._stop_requested:
                            self.sequence_resumed.emit()
                            logger.info(f"Test sequence resumed, continuing with test {i+2}/{total_tests}")
                        self._pause_lock.unlock()
                    else:
                        # Last test - still pause to allow user to review before sequence ends
                        # Note: This is a soft pause - sequence will end after resume
                        self._pause_lock.lock()
                        self._is_paused = True
                        self.sequence_paused.emit()
                        logger.info(f"Test sequence paused after final test {i+1}/{total_tests}")
                        
                        # Wait until resume is called (or timeout)
                        while self._is_paused and not self._stop_requested:
                            self._pause_condition.wait(self._pause_lock, 100)  # Wait 100ms at a time
                        
                        if not self._stop_requested:
                            self.sequence_resumed.emit()
                            logger.info("Test sequence resumed after final test")
                        self._pause_lock.unlock()
            
            # Generate summary
            if cancelled:
                self.sequence_cancelled.emit()
                summary = f"Sequence cancelled after {len(results)}/{total_tests} tests"
            else:
                pass_count = sum(1 for _, success, _ in results if success)
                pass_rate = pass_count / len(results) * 100 if results else 0
                avg_time = sum(exec_times) / len(exec_times) if exec_times else 0
                failure_reasons = [info for _, success, info in results if not success]
                failure_summary = '\n'.join(set(failure_reasons)) if failure_reasons else 'None'
                
                summary = (
                    f"Sequence completed: {pass_count}/{len(results)} passed ({pass_rate:.1f}%)\n"
                    f"Average execution time: {avg_time:.2f}s\n"
                    f"Failure reasons: {failure_summary}"
                )
            
            # Emit sequence finished signal
            self.sequence_finished.emit(results, summary)
            logger.info(f"Test sequence completed: {len(results)}/{total_tests} tests")
            
        except Exception as e:
            logger.error(f"Test sequence execution failed: {e}", exc_info=True)
            self.sequence_finished.emit(results, f"Sequence failed: {e}")
    
    def is_running(self) -> bool:
        """Check if thread is currently executing tests.
        
        Returns:
            True if thread is running, False otherwise
        """
        return self.isRunning()

