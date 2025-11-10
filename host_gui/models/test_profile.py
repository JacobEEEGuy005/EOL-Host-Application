"""
Test Profile model for representing test configurations.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class ActuationConfig:
    """Configuration for test actuation (Digital Logic Test, Analog Sweep Test, Phase Current Test, Analog Static Test, or Temperature Validation Test).
    
    Attributes:
        type: Test type ('Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', or 'Temperature Validation Test')
        can_id: CAN message ID for actuation commands (digital tests)
        signal: Signal name for actuation (optional)
        value_low: Low value for digital tests
        value_high: High value for digital tests
        dwell_ms: Dwell time in milliseconds
        
        For analog tests:
        dac_can_id: CAN ID for DAC command message
        dac_command_signal: Signal name for DAC command
        mux_enable_signal: Signal name for MUX enable
        mux_channel_signal: Signal name for MUX channel selection
        mux_channel_value: MUX channel value
        dac_min_mv: Minimum DAC voltage in millivolts
        dac_max_mv: Maximum DAC voltage in millivolts
        dac_step_mv: DAC voltage step in millivolts
        dac_dwell_ms: Dwell time per DAC voltage step
        
        For Phase Current Test:
        message_type: CAN message type for phase current test command
        device_id: Target device ID (IPC_Hardware = 0x03)
        enable_signal: Signal name for enabling phase current test
        id_ref_signal: Signal name for Id reference current
        iq_ref_signal: Signal name for Iq reference current
        test_points: List of (Id_ref, Iq_ref) test points
        oscilloscope: Oscilloscope configuration dictionary
        timing: Timing configuration dictionary
        data_collection: Data collection configuration dictionary
        steady_state_detection: Steady-state detection configuration dictionary
        
        For Analog Static Test:
        feedback_signal_source: CAN message ID containing feedback signal
        feedback_signal: Signal name for feedback signal
        eol_signal_source: CAN message ID containing EOL signal
        eol_signal: Signal name for EOL signal
        tolerance_mv: Tolerance in millivolts for pass/fail determination
        pre_dwell_time_ms: Pre-dwell time in milliseconds (system stabilization)
        dwell_time_ms: Dwell time in milliseconds (data collection period)
        
        For Temperature Validation Test:
        feedback_signal_source: CAN message ID containing temperature signal
        feedback_signal: Signal name for temperature signal
        reference_temperature_c: Reference temperature in degrees Celsius
        tolerance_c: Tolerance in degrees Celsius for pass/fail determination
        dwell_time_ms: Dwell time in milliseconds (data collection period)
    """
    type: str  # 'Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', or 'Temperature Validation Test'
    
    # Digital test fields
    can_id: Optional[int] = None
    signal: Optional[str] = None
    value_low: Optional[str] = None
    value_high: Optional[str] = None
    dwell_ms: Optional[int] = None
    
    # Analog test fields
    dac_can_id: Optional[int] = None
    dac_command_signal: Optional[str] = None
    mux_enable_signal: Optional[str] = None
    mux_channel_signal: Optional[str] = None
    mux_channel_value: Optional[int] = None
    dac_min_mv: Optional[int] = None
    dac_max_mv: Optional[int] = None
    dac_step_mv: Optional[int] = None
    dac_dwell_ms: Optional[int] = None
    
    # Phase Current Calibration test fields
    message_type: Optional[int] = None
    device_id: Optional[int] = None
    enable_signal: Optional[str] = None  # "Mctrl_Phase_I_Test_Enable"
    id_ref_signal: Optional[str] = None  # "Mctrl_Set_Id_Ref"
    iq_ref_signal: Optional[str] = None  # "Mctrl_Set_Iq_Ref"
    test_points: Optional[List[Dict[str, float]]] = None
    oscilloscope: Optional[Dict[str, Any]] = None
    timing: Optional[Dict[str, int]] = None
    data_collection: Optional[Dict[str, Any]] = None
    steady_state_detection: Optional[Dict[str, Any]] = None
    
    # Analog Static Test fields
    feedback_signal_source: Optional[int] = None  # CAN message ID
    feedback_signal: Optional[str] = None  # Signal name
    eol_signal_source: Optional[int] = None  # CAN message ID
    eol_signal: Optional[str] = None  # Signal name
    tolerance_mv: Optional[float] = None  # Tolerance in millivolts
    pre_dwell_time_ms: Optional[int] = None  # Pre-dwell time in milliseconds
    dwell_time_ms: Optional[int] = None  # Dwell time in milliseconds
    
    # Temperature Validation Test fields
    reference_temperature_c: Optional[float] = None  # Reference temperature in degrees Celsius
    tolerance_c: Optional[float] = None  # Tolerance in degrees Celsius
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format (for JSON serialization)."""
        result = {'type': self.type}
        if self.type == 'Digital Logic Test':
            if self.can_id is not None:
                result['can_id'] = self.can_id
            if self.signal:
                result['signal'] = self.signal
            if self.value_low:
                result['value_low'] = self.value_low
            if self.value_high:
                result['value_high'] = self.value_high
            if self.dwell_ms is not None:
                result['dwell_ms'] = self.dwell_ms
        elif self.type == 'Analog Sweep Test':
            if self.dac_can_id is not None:
                result['dac_can_id'] = self.dac_can_id
            if self.dac_command_signal:
                result['dac_command_signal'] = self.dac_command_signal
            if self.mux_enable_signal:
                result['mux_enable_signal'] = self.mux_enable_signal
            if self.mux_channel_signal:
                result['mux_channel_signal'] = self.mux_channel_signal
            if self.mux_channel_value is not None:
                result['mux_channel_value'] = self.mux_channel_value
            if self.dac_min_mv is not None:
                result['dac_min_mv'] = self.dac_min_mv
            if self.dac_max_mv is not None:
                result['dac_max_mv'] = self.dac_max_mv
            if self.dac_step_mv is not None:
                result['dac_step_mv'] = self.dac_step_mv
            if self.dac_dwell_ms is not None:
                result['dac_dwell_ms'] = self.dac_dwell_ms
        elif self.type == 'Phase Current Test':
            if self.can_id is not None:
                result['can_id'] = self.can_id
            if self.message_type is not None:
                result['message_type'] = self.message_type
            if self.device_id is not None:
                result['device_id'] = self.device_id
            if self.enable_signal:
                result['enable_signal'] = self.enable_signal
            if self.id_ref_signal:
                result['id_ref_signal'] = self.id_ref_signal
            if self.iq_ref_signal:
                result['iq_ref_signal'] = self.iq_ref_signal
            if self.test_points:
                result['test_points'] = self.test_points
            if self.oscilloscope:
                result['oscilloscope'] = self.oscilloscope
            if self.timing:
                result['timing'] = self.timing
            if self.data_collection:
                result['data_collection'] = self.data_collection
            if self.steady_state_detection:
                result['steady_state_detection'] = self.steady_state_detection
        elif self.type == 'Analog Static Test':
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.feedback_signal:
                result['feedback_signal'] = self.feedback_signal
            if self.eol_signal_source is not None:
                result['eol_signal_source'] = self.eol_signal_source
            if self.eol_signal:
                result['eol_signal'] = self.eol_signal
            if self.tolerance_mv is not None:
                result['tolerance_mv'] = self.tolerance_mv
            if self.pre_dwell_time_ms is not None:
                result['pre_dwell_time_ms'] = self.pre_dwell_time_ms
            if self.dwell_time_ms is not None:
                result['dwell_time_ms'] = self.dwell_time_ms
        elif self.type == 'Temperature Validation Test':
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.feedback_signal:
                result['feedback_signal'] = self.feedback_signal
            if self.reference_temperature_c is not None:
                result['reference_temperature_c'] = self.reference_temperature_c
            if self.tolerance_c is not None:
                result['tolerance_c'] = self.tolerance_c
            if self.dwell_time_ms is not None:
                result['dwell_time_ms'] = self.dwell_time_ms
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActuationConfig':
        """Create from dictionary format."""
        return cls(**data)


@dataclass
class TestProfile:
    """Represents a test configuration profile.
    
    Attributes:
        name: Test name/identifier
        actuation: Actuation configuration
        feedback_signal: Signal name to monitor for feedback
        feedback_message_id: CAN message ID containing feedback signal
    """
    name: str
    actuation: ActuationConfig
    feedback_signal: Optional[str] = None
    feedback_message_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format (for JSON serialization)."""
        result = {
            'name': self.name,
            'actuation': self.actuation.to_dict()
        }
        if self.feedback_signal:
            result['feedback_signal'] = self.feedback_signal
        if self.feedback_message_id is not None:
            result['feedback_message_id'] = self.feedback_message_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestProfile':
        """Create from dictionary format."""
        actuation_data = data.get('actuation', {})
        actuation = ActuationConfig.from_dict(actuation_data)
        return cls(
            name=data.get('name', 'Unnamed Test'),
            actuation=actuation,
            feedback_signal=data.get('feedback_signal'),
            feedback_message_id=data.get('feedback_message_id')
        )

