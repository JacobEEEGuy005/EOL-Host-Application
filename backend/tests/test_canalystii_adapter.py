"""Unit tests for Canalystii adapter implementation.

These tests verify:
- Channel validation (must be '0' or '1')
- Bitrate conversion (kbps to bps)
- Interface parameter passing
- Error handling for invalid configurations
- Error handling when canalystii package is missing
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

try:
    import can
except Exception:
    can = None

from backend.adapters.python_can_adapter import PythonCanAdapter
from backend.adapters.interface import Frame


@pytest.mark.skipif(can is None, reason="python-can not installed")
class TestCanalystiiChannelValidation:
    """Test channel validation for Canalystii adapter."""
    
    def test_valid_channel_0_string(self):
        """Test that channel '0' is accepted."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=500000)
        assert adapter.channel == '0'
    
    def test_valid_channel_1_string(self):
        """Test that channel '1' is accepted."""
        adapter = PythonCanAdapter(channel='1', interface='canalystii', bitrate=500000)
        assert adapter.channel == '1'
    
    def test_valid_channel_0_int(self):
        """Test that channel 0 (int) is accepted and normalized to string."""
        adapter = PythonCanAdapter(channel=0, interface='canalystii', bitrate=500000)
        assert adapter.channel == '0'
        assert isinstance(adapter.channel, str)
    
    def test_valid_channel_1_int(self):
        """Test that channel 1 (int) is accepted and normalized to string."""
        adapter = PythonCanAdapter(channel=1, interface='canalystii', bitrate=500000)
        assert adapter.channel == '1'
        assert isinstance(adapter.channel, str)
    
    def test_invalid_channel_string(self):
        """Test that invalid channel string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Canalystii channel"):
            PythonCanAdapter(channel='2', interface='canalystii', bitrate=500000)
    
    def test_invalid_channel_int(self):
        """Test that invalid channel int raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Canalystii channel"):
            PythonCanAdapter(channel=2, interface='canalystii', bitrate=500000)
    
    def test_invalid_channel_none(self):
        """Test that None channel raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Canalystii channel"):
            PythonCanAdapter(channel=None, interface='canalystii', bitrate=500000)


@pytest.mark.skipif(can is None, reason="python-can not installed")
class TestCanalystiiBitrateValidation:
    """Test bitrate validation and warnings for Canalystii."""
    
    @patch('backend.adapters.python_can_adapter.logger')
    def test_valid_bitrate_500k(self, mock_logger):
        """Test that common bitrate 500k bps doesn't warn."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=500000)
        # Should not log warning
        mock_logger.warning.assert_not_called()
    
    @patch('backend.adapters.python_can_adapter.logger')
    def test_valid_bitrate_250k(self, mock_logger):
        """Test that common bitrate 250k bps doesn't warn."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=250000)
        mock_logger.warning.assert_not_called()
    
    @patch('backend.adapters.python_can_adapter.logger')
    def test_valid_bitrate_125k(self, mock_logger):
        """Test that common bitrate 125k bps doesn't warn."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=125000)
        mock_logger.warning.assert_not_called()
    
    @patch('backend.adapters.python_can_adapter.logger')
    def test_uncommon_bitrate_warns(self, mock_logger):
        """Test that uncommon bitrate logs a warning."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=333333)
        # Should log warning about uncommon bitrate
        mock_logger.warning.assert_called_once()
        assert 'Uncommon bitrate' in mock_logger.warning.call_args[0][0]
    
    def test_no_bitrate_provided(self):
        """Test that None bitrate is accepted."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=None)
        assert adapter.bitrate is None


@pytest.mark.skipif(can is None, reason="python-can not installed")
class TestCanalystiiInterfaceParameter:
    """Test that interface parameter is passed correctly."""
    
    @patch('backend.adapters.python_can_adapter.can')
    def test_interface_parameter_passed(self, mock_can_module):
        """Test that interface='canalystii' is passed to python-can Bus."""
        mock_bus = MagicMock()
        mock_can_module.Bus = MagicMock(return_value=mock_bus)
        
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=500000)
        
        # Mock canalystii import
        with patch('builtins.__import__', side_effect=lambda name, *args: MagicMock()):
            adapter.open()
        
        # Verify Bus was called with correct interface
        mock_can_module.Bus.assert_called_once()
        call_kwargs = mock_can_module.Bus.call_args[1]
        assert call_kwargs['interface'] == 'canalystii'
        assert call_kwargs['channel'] == '0'
        assert call_kwargs['bitrate'] == 500000
    
    @patch('backend.adapters.python_can_adapter.can')
    def test_bitrate_passed_correctly(self, mock_can_module):
        """Test that bitrate in bps is passed correctly."""
        mock_bus = MagicMock()
        mock_can_module.Bus = MagicMock(return_value=mock_bus)
        
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=500000)
        
        with patch('builtins.__import__', side_effect=lambda name, *args: MagicMock()):
            adapter.open()
        
        call_kwargs = mock_can_module.Bus.call_args[1]
        assert call_kwargs['bitrate'] == 500000  # Should be in bps


@pytest.mark.skipif(can is None, reason="python-can not installed")
class TestCanalystiiErrorHandling:
    """Test error handling for Canalystii-specific issues."""
    
    def test_missing_canalystii_package(self):
        """Test error when canalystii package is not installed."""
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=500000)
        
        # Mock ImportError for canalystii
        with patch('builtins.__import__', side_effect=ImportError("No module named 'canalystii'")):
            with pytest.raises(RuntimeError, match="Canalystii adapter requires"):
                adapter.open()
    
    @patch('backend.adapters.python_can_adapter.can')
    def test_connection_error_message(self, mock_can_module):
        """Test that connection errors provide helpful messages."""
        mock_can_module.Bus = MagicMock(side_effect=Exception("Device not found"))
        
        adapter = PythonCanAdapter(channel='0', interface='canalystii', bitrate=500000)
        
        with patch('builtins.__import__', side_effect=lambda name, *args: MagicMock()):
            with pytest.raises(RuntimeError, match="Failed to open Canalystii adapter"):
                adapter.open()
            # Verify error message mentions device connection
            try:
                adapter.open()
            except RuntimeError as e:
                assert 'device is connected' in str(e).lower()


@pytest.mark.skipif(can is None, reason="python-can not installed")
class TestCanalystiiNonCanalystiiInterface:
    """Test that non-Canalystii interfaces don't trigger Canalystii-specific validation."""
    
    def test_other_interface_no_channel_validation(self):
        """Test that other interfaces don't validate channel."""
        # This should not raise an error for invalid channel when interface is not canalystii
        adapter = PythonCanAdapter(channel='invalid', interface='socketcan', bitrate=500000)
        assert adapter.channel == 'invalid'  # No validation for non-canalystii
    
    def test_other_interface_no_bitrate_validation(self):
        """Test that other interfaces don't validate bitrate."""
        adapter = PythonCanAdapter(channel='can0', interface='socketcan', bitrate=999999)
        assert adapter.bitrate == 999999  # No validation for non-canalystii
    
    def test_no_interface_no_validation(self):
        """Test that no interface specified doesn't trigger validation."""
        adapter = PythonCanAdapter(channel='virtual', bitrate=500000)
        assert adapter.channel == 'virtual'


@pytest.mark.skipif(can is None, reason="python-can not installed")
class TestCanalystiiIntegration:
    """Integration tests that require python-can (but may not require actual hardware)."""
    
    @patch('backend.adapters.python_can_adapter.can')
    def test_full_initialization(self, mock_can_module):
        """Test full adapter initialization with all parameters."""
        mock_bus = MagicMock()
        mock_can_module.Bus = MagicMock(return_value=mock_bus)
        
        adapter = PythonCanAdapter(
            channel='1',
            interface='canalystii',
            bitrate=250000
        )
        
        assert adapter.channel == '1'
        assert adapter.interface == 'canalystii'
        assert adapter.bitrate == 250000
        
        with patch('builtins.__import__', side_effect=lambda name, *args: MagicMock()):
            adapter.open()
        
        assert adapter._bus is not None
        adapter.close()
        assert adapter._bus is None

