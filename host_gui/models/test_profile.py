"""
Test Profile model for representing test configurations.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ActuationConfig:
    """Configuration for test actuation (digital or analog).
    
    Attributes:
        type: Test type ('digital' or 'analog')
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
    """
    type: str  # 'digital' or 'analog'
    
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format (for JSON serialization)."""
        result = {'type': self.type}
        if self.type == 'digital':
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
        else:  # analog
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

