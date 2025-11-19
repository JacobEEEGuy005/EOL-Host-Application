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
    test_mode_mismatch = QtCore.Signal(str, str)  # test_name, message
    
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
            i = 0
            while i < total_tests:
                if self._stop_requested:
                    logger.info(f"Test execution cancelled at test {i+1}/{total_tests}")
                    cancelled = True
                    break
                
                test = self.tests[i]
                self._current_test_index = i
                test_name = test.get('name', '<unnamed>')
                
                # Emit test started signal
                self.test_started.emit(i, test_name)
                self.sequence_progress.emit(i, total_tests)
                
                logger.info(f"Executing test {i+1}/{total_tests}: {test_name}")
                
                # Check test mode before executing test
                test_mode_check_passed = False
                while not test_mode_check_passed:
                    # Check if paused or cancelled
                    if self._stop_requested:
                        cancelled = True
                        break
                    
                    # Perform test mode check
                    check_passed, check_msg = self.test_runner.check_test_mode(test)
                    
                    if check_passed:
                        test_mode_check_passed = True
                        logger.info(f"Test mode check passed for {test_name}: {check_msg}")
                    else:
                        # Pause test sequence
                        self._pause_lock.lock()
                        self._is_paused = True
                        self.sequence_paused.emit()
                        
                        # Show warning dialog (must be done in main thread via signal)
                        logger.warning(f"Test mode mismatch for {test_name}: {check_msg}")
                        self.test_mode_mismatch.emit(test_name, check_msg)
                        
                        # Wait for resume
                        logger.info(f"Waiting for resume after test mode mismatch for {test_name}")
                        self._pause_condition.wait(self._pause_lock)
                        self._is_paused = False
                        self._pause_lock.unlock()
                        
                        # When resumed, loop will check again
                        logger.info(f"Resumed after test mode mismatch for {test_name}, re-checking...")
                
                # If cancelled during test mode check, break out
                if self._stop_requested:
                    cancelled = True
                    break
                
                start_time = time.time()
                test_paused = False  # Flag to track if test requested pause (not a failure)
                try:
                    # Execute test (this may take time)
                    success, info = self.test_runner.run_single_test(test, self.timeout)
                    end_time = time.time()
                    exec_time = end_time - start_time
                    
                    # Check if this is a pause request (not a failure)
                    # Pause requests have info messages starting with "Test sequence paused"
                    if not success and info and info.startswith("Test sequence paused"):
                        test_paused = True
                        logger.info(f"Test {i+1} requested pause (not a failure): {info}")
                        
                        # Don't record as result, don't emit test_finished
                        # Just pause and wait for resume
                        # When resumed, this test will be retried (i doesn't increment)
                    else:
                        # Normal test completion (pass or fail)
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
                
                # Emit progress update (only if test completed, not paused)
                if not test_paused:
                    progress = (i + 1) / total_tests
                    self.test_progress.emit(progress)
                
                # Check for pause request after test completes (but before next test starts)
                # Also handle test-paused case (when test itself requested pause)
                if self._pause_requested or test_paused:
                    # Pause the sequence
                    self._pause_lock.lock()
                    self._is_paused = True
                    self.sequence_paused.emit()
                    
                    if test_paused:
                        # Test requested pause (e.g., user declined safety check)
                        logger.info(f"Test sequence paused by test {i+1}/{total_tests} (test will be retried on resume)")
                    elif i < total_tests - 1:
                        # User clicked pause button - pause before next test
                        logger.info(f"Test sequence paused after test {i+1}/{total_tests}")
                    else:
                        # Last test - pause to allow user to review before sequence ends
                        logger.info(f"Test sequence paused after final test {i+1}/{total_tests}")
                    
                    # Wait until resume is called
                    while self._is_paused and not self._stop_requested:
                        self._pause_condition.wait(self._pause_lock, 100)  # Wait 100ms at a time
                    
                    if not self._stop_requested:
                        self.sequence_resumed.emit()
                        if test_paused:
                            # Test was paused - retry the same test (don't increment i)
                            logger.info(f"Test sequence resumed, retrying test {i+1}/{total_tests}")
                            # Clear pause flags for retry
                            self._pause_requested = False
                            self._pause_lock.unlock()
                            continue  # Retry the same test (don't increment i)
                        elif i < total_tests - 1:
                            logger.info(f"Test sequence resumed, continuing with test {i+2}/{total_tests}")
                        else:
                            logger.info("Test sequence resumed after final test")
                    self._pause_lock.unlock()
                
                # Increment test index for next iteration (unless test was paused and will be retried)
                if not test_paused:
                    i += 1
            
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

