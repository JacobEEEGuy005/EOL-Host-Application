"""
Custom exception classes for EOL Host GUI application.

This module provides specific exception types for different error scenarios,
improving error handling clarity and enabling better error recovery.
"""

from typing import Any


class EolHostException(Exception):
    """Base exception for all EOL Host application errors.
    
    All custom exceptions should inherit from this class to enable
    catching all application-specific errors while preserving exception
    hierarchy.
    """
    pass


class CanAdapterError(EolHostException):
    """Exception raised for CAN adapter connection or operation failures.
    
    Attributes:
        adapter_type: Type of adapter that failed (e.g., 'PCAN', 'SimAdapter')
        operation: Operation that failed (e.g., 'connect', 'send_frame')
        original_error: The underlying exception that caused this error
    """
    
    def __init__(self, message: str, adapter_type: str = None, operation: str = None, original_error: Exception = None):
        """Initialize CanAdapterError.
        
        Args:
            message: Human-readable error message
            adapter_type: Type of adapter (optional)
            operation: Operation that failed (optional)
            original_error: Underlying exception (optional)
        """
        super().__init__(message)
        self.adapter_type = adapter_type
        self.operation = operation
        self.original_error = original_error


class DbcError(EolHostException):
    """Exception raised for DBC file loading or parsing failures.
    
    Attributes:
        dbc_path: Path to the DBC file that failed
        operation: Operation that failed (e.g., 'load', 'parse', 'find_message')
        original_error: The underlying exception that caused this error
    """
    
    def __init__(self, message: str, dbc_path: str = None, operation: str = None, original_error: Exception = None):
        """Initialize DbcError.
        
        Args:
            message: Human-readable error message
            dbc_path: Path to DBC file (optional)
            operation: Operation that failed (optional)
            original_error: Underlying exception (optional)
        """
        super().__init__(message)
        self.dbc_path = dbc_path
        self.operation = operation
        self.original_error = original_error


class TestExecutionError(EolHostException):
    """Exception raised during test execution failures.
    
    Attributes:
        test_name: Name of the test that failed
        test_type: Type of test ('digital' or 'analog')
        stage: Stage of execution that failed (e.g., 'actuation', 'feedback_check')
        original_error: The underlying exception that caused this error
    """
    
    def __init__(self, message: str, test_name: str = None, test_type: str = None, 
                 stage: str = None, original_error: Exception = None):
        """Initialize TestExecutionError.
        
        Args:
            message: Human-readable error message
            test_name: Name of test (optional)
            test_type: Type of test (optional)
            stage: Execution stage (optional)
            original_error: Underlying exception (optional)
        """
        super().__init__(message)
        self.test_name = test_name
        self.test_type = test_type
        self.stage = stage
        self.original_error = original_error


class ConfigurationError(EolHostException):
    """Exception raised for invalid configuration values.
    
    Attributes:
        setting_name: Name of the setting that is invalid
        setting_value: The invalid value
        expected: Description of expected value
    """
    
    def __init__(self, message: str, setting_name: str = None, setting_value: Any = None, 
                 expected: str = None):
        """Initialize ConfigurationError.
        
        Args:
            message: Human-readable error message
            setting_name: Name of invalid setting (optional)
            setting_value: Invalid value (optional)
            expected: Expected value description (optional)
        """
        super().__init__(message)
        self.setting_name = setting_name
        self.setting_value = setting_value
        self.expected = expected


class SignalDecodeError(EolHostException):
    """Exception raised for signal decoding failures.
    
    Attributes:
        can_id: CAN message ID that failed to decode
        signal_name: Name of signal that failed (if applicable)
        data: Raw data bytes that failed to decode
        original_error: The underlying exception that caused this error
    """
    
    def __init__(self, message: str, can_id: int = None, signal_name: str = None,
                 data: bytes = None, original_error: Exception = None):
        """Initialize SignalDecodeError.
        
        Args:
            message: Human-readable error message
            can_id: CAN message ID (optional)
            signal_name: Signal name (optional)
            data: Raw data bytes (optional)
            original_error: Underlying exception (optional)
        """
        super().__init__(message)
        self.can_id = can_id
        self.signal_name = signal_name
        self.data = data
        self.original_error = original_error

