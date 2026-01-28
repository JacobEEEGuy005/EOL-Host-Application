"""
Test Profile model for representing test configurations.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class ActuationConfig:
    """Configuration for test actuation (Digital Logic Test, Analog Sweep Test, Phase Current Test, Analog Static Test, Analog PWM Sensor, Temperature Validation Test, Fan Control Test, or Charged HV Bus Test).
    
    Attributes:
        type: Test type ('Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', or 'Charged HV Bus Test')
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
        
        For Analog PWM Sensor Test:
        feedback_signal_source: CAN message ID containing PWM frequency and duty signals
        feedback_pwm_frequency_signal: Signal name for PWM frequency measurement (in Hz)
        feedback_duty_signal: Signal name for PWM duty cycle measurement (in percentage %)
        reference_pwm_frequency: Reference PWM frequency in Hz
        reference_duty: Reference duty cycle in percentage (%)
        pwm_frequency_tolerance: Tolerance for PWM frequency in Hz
        duty_tolerance: Tolerance for duty cycle in percentage (%)
        acquisition_time_ms: Time to collect PWM data in milliseconds
        
        For Fan Control Test:
        fan_test_trigger_source: CAN message ID for fan test trigger command
        fan_test_trigger_signal: Signal name for fan test trigger
        fan_control_feedback_source: CAN message ID containing fan feedback signals
        fan_enabled_signal: Signal name for fan enabled status
        fan_tach_feedback_signal: Signal name for fan tach feedback
        fan_fault_feedback_signal: Signal name for fan fault feedback
        dwell_time_ms: Dwell time in milliseconds (data collection period)
        test_timeout_ms: Test timeout in milliseconds (for fan enabled verification)
        
        For External 5V Test:
        ext_5v_test_trigger_source: CAN message ID for External 5V test trigger command
        ext_5v_test_trigger_signal: Signal name for External 5V test trigger
        eol_ext_5v_measurement_source: CAN message ID containing EOL Ext 5V measurement signal
        eol_ext_5v_measurement_signal: Signal name for EOL Ext 5V measurement
        feedback_signal_source: CAN message ID containing feedback signal
        feedback_signal: Signal name for feedback signal
        tolerance_mv: Tolerance in millivolts for pass/fail determination
        pre_dwell_time_ms: Pre-dwell time in milliseconds (system stabilization)
        dwell_time_ms: Dwell time in milliseconds (data collection period)
        
        For DC Bus Sensing:
        oscilloscope_channel: Channel name from oscilloscope configuration (e.g., "DC Bus Voltage")
        feedback_signal_source: CAN message ID containing feedback signal
        feedback_signal: Signal name for feedback signal
        dwell_time_ms: Dwell time in milliseconds (data collection period)
        tolerance_v: Tolerance in volts for pass/fail determination
        
        For Output Current Calibration:
        test_trigger_source: CAN message ID for test trigger command
        test_trigger_signal: Signal name for test trigger (enable/disable test mode)
        test_trigger_signal_value: Value to send for test trigger signal (typically 1 to enable, 0 to disable)
        current_setpoint_signal: Signal name for setting output current setpoint
        output_current_trim_signal: Signal name for output current trim value (initialization)
        initial_trim_value: Initial trim value in percent to initialize DUT before test (0.0000-200.0000)
        feedback_signal_source: CAN message ID for feedback signal (DUT current measurement)
        feedback_signal: Signal name for output current feedback from DUT
        oscilloscope_channel: Channel name from oscilloscope configuration for current measurement
        oscilloscope_timebase: Oscilloscope timebase setting ("10MS", "20MS", "100MS", or "500MS")
        minimum_test_current: Minimum current setpoint in Amperes
        maximum_test_current: Maximum current setpoint in Amperes
        step_current: Current step size in Amperes for sweep
        pre_acquisition_time_ms: Time to wait before starting data acquisition (stabilization time)
        acquisition_time_ms: Time to collect data from both CAN and oscilloscope
        tolerance_percent: Maximum allowed gain error percentage
        
        For Charged HV Bus Test:
        command_signal_source: CAN message ID for command messages
        test_trigger_signal: Signal name for test trigger command
        test_trigger_signal_value: Value to send for test trigger signal (user configurable, 0-255)
        set_output_current_trim_signal: Signal name for setting output current trim value
        fallback_output_current_trim_value: Fallback trim value (0-200%) if Output Current Calibration not performed
        set_output_current_setpoint_signal: Signal name for setting output current setpoint
        output_test_current: Output current setpoint in Amperes (0-40A)
        feedback_signal_source: CAN message ID for feedback messages
        dut_test_state_signal: Signal name for DUT test state feedback
        enable_relay_signal: Signal name for AC relay enable feedback
        enable_pfc_signal: Signal name for PFC enable feedback
        pfc_power_good_signal: Signal name for PFC power good feedback
        pcmc_signal: Signal name for Peak Current Mode Control feedback
        psfb_fault_signal: Signal name for PSFB fault feedback (for future use)
        test_time_ms: Test duration in milliseconds from test trigger (minimum 1000)
        
        For Charger Functional Test:
        command_signal_source: CAN message ID for command messages
        test_trigger_signal: Signal name for test trigger command
        test_trigger_signal_value: Value to send for test trigger signal (user configurable, 0-255)
        set_output_current_trim_signal: Signal name for setting output current trim value
        fallback_output_current_trim_value: Fallback trim value (0-200%) if Output Current Calibration not performed
        set_output_current_setpoint_signal: Signal name for setting output current setpoint
        output_test_current: Output current setpoint in Amperes (0-40A)
        feedback_signal_source: CAN message ID for feedback messages
        dut_test_state_signal: Signal name for DUT test state feedback
        enable_relay_signal: Signal name for AC relay enable feedback
        enable_pfc_signal: Signal name for PFC enable feedback
        pfc_power_good_signal: Signal name for PFC power good feedback
        pcmc_signal: Signal name for Peak Current Mode Control feedback
        output_current_signal: Signal name for output current feedback
        psfb_fault_signal: Signal name for PSFB fault feedback
        output_current_tolerance: Tolerance for output current regulation in Amperes (>= 0)
        test_time_ms: Test duration in milliseconds from test trigger (minimum 1000)
        
        For Phase Offset Calibration Test:
        test_request_source: CAN message ID for test request command (typically 272)
        test_request_signal: Signal name for test request (typically "Test_Request")
        test_request_value: Value to send for test request signal (typically 1 to enable Drive Mode)
        feedback_signal_source: CAN message ID for feedback messages (typically 250)
        calib_state_signal: Signal name for calibration status (typically "PhaseOffset_Calib_Status")
        phase_v_offset_signal: Signal name for Phase V ADC offset (typically "PhaseV_ADC_Offset")
        phase_w_offset_signal: Signal name for Phase W ADC offset (typically "PhaseW_ADC_Offset")
        calibration_timeout_ms: Timeout in milliseconds to wait for CAL_DONE status (minimum 1000, default 5000)
    """
    type: str  # 'Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test', or 'Phase Offset Calibration Test'
    
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
    
    # Analog PWM Sensor Test fields
    feedback_pwm_frequency_signal: Optional[str] = None  # Signal name for PWM frequency measurement (in Hz)
    feedback_duty_signal: Optional[str] = None  # Signal name for PWM duty cycle measurement (in percentage %)
    reference_pwm_frequency: Optional[float] = None  # Reference PWM frequency in Hz
    reference_duty: Optional[float] = None  # Reference duty cycle in percentage (%)
    pwm_frequency_tolerance: Optional[float] = None  # Tolerance for PWM frequency in Hz
    duty_tolerance: Optional[float] = None  # Tolerance for duty cycle in percentage (%)
    # Note: feedback_signal_source is already defined for Analog Static Test
    # Note: acquisition_time_ms is already defined for Output Current Calibration
    
    # Fan Control Test fields
    fan_test_trigger_source: Optional[int] = None  # CAN message ID for fan test trigger
    fan_test_trigger_signal: Optional[str] = None  # Signal name for fan test trigger
    fan_control_feedback_source: Optional[int] = None  # CAN message ID containing fan feedback signals
    fan_enabled_signal: Optional[str] = None  # Signal name for fan enabled status
    fan_tach_feedback_signal: Optional[str] = None  # Signal name for fan tach feedback
    fan_fault_feedback_signal: Optional[str] = None  # Signal name for fan fault feedback
    test_timeout_ms: Optional[int] = None  # Test timeout in milliseconds
    
    # External 5V Test fields
    ext_5v_test_trigger_source: Optional[int] = None  # CAN message ID for External 5V test trigger
    ext_5v_test_trigger_signal: Optional[str] = None  # Signal name for External 5V test trigger
    eol_ext_5v_measurement_source: Optional[int] = None  # CAN message ID containing EOL Ext 5V measurement
    eol_ext_5v_measurement_signal: Optional[str] = None  # Signal name for EOL Ext 5V measurement
    # Note: feedback_signal_source and feedback_signal are already defined for Analog Static Test
    # tolerance_mv, pre_dwell_time_ms, and dwell_time_ms are also already defined
    
    # DC Bus Sensing Test fields
    oscilloscope_channel: Optional[str] = None  # Channel name from oscilloscope configuration
    # Note: feedback_signal_source and feedback_signal are already defined for Analog Static Test
    # Note: dwell_time_ms is already defined
    tolerance_v: Optional[float] = None  # Tolerance in volts
    
    # Output Current Calibration Test fields
    test_trigger_source: Optional[int] = None  # CAN message ID for test trigger command
    test_trigger_signal: Optional[str] = None  # Signal name for test trigger
    test_trigger_signal_value: Optional[int] = None  # Value to send for test trigger signal (0-255)
    current_setpoint_signal: Optional[str] = None  # Signal name for setting output current setpoint
    output_current_trim_signal: Optional[str] = None  # Signal name for output current trim value (initialization)
    initial_trim_value: Optional[float] = None  # Initial trim value in percent (0.0000-200.0000)
    # Note: feedback_signal_source and feedback_signal are already defined
    # Note: oscilloscope_channel is already defined
    oscilloscope_timebase: Optional[str] = None  # Oscilloscope timebase setting ("10MS", "20MS", "100MS", or "500MS")
    minimum_test_current: Optional[float] = None  # Minimum current setpoint in Amperes
    maximum_test_current: Optional[float] = None  # Maximum current setpoint in Amperes
    step_current: Optional[float] = None  # Current step size in Amperes for sweep
    pre_acquisition_time_ms: Optional[int] = None  # Time to wait before starting data acquisition
    acquisition_time_ms: Optional[int] = None  # Time to collect data from both CAN and oscilloscope
    tolerance_percent: Optional[float] = None  # Maximum allowed gain error percentage
    
    # Charged HV Bus Test fields
    command_signal_source: Optional[int] = None  # CAN message ID for command messages
    test_trigger_signal: Optional[str] = None  # Signal name for test trigger command (reused from Output Current Calibration)
    test_trigger_signal_value: Optional[int] = None  # Value to send for test trigger signal (reused from Output Current Calibration)
    set_output_current_trim_signal: Optional[str] = None  # Signal name for setting output current trim value
    fallback_output_current_trim_value: Optional[float] = None  # Fallback trim value (0-200%)
    set_output_current_setpoint_signal: Optional[str] = None  # Signal name for setting output current setpoint (reused from Output Current Calibration)
    output_test_current: Optional[float] = None  # Output current setpoint in Amperes (0-40A)
    # Note: feedback_signal_source is already defined for Analog Static Test
    dut_test_state_signal: Optional[str] = None  # Signal name for DUT test state feedback
    enable_relay_signal: Optional[str] = None  # Signal name for AC relay enable feedback
    enable_pfc_signal: Optional[str] = None  # Signal name for PFC enable feedback
    pfc_power_good_signal: Optional[str] = None  # Signal name for PFC power good feedback
    pcmc_signal: Optional[str] = None  # Signal name for Peak Current Mode Control feedback
    psfb_fault_signal: Optional[str] = None  # Signal name for PSFB fault feedback
    test_time_ms: Optional[int] = None  # Test duration in milliseconds from test trigger
    
    # Charger Functional Test fields
    output_current_signal: Optional[str] = None  # Signal name for output current feedback
    output_current_tolerance: Optional[float] = None  # Tolerance for output current regulation in Amperes
    
    # Phase Offset Calibration Test fields
    test_request_source: Optional[int] = None  # CAN message ID for test request command (typically 272)
    test_request_signal: Optional[str] = None  # Signal name for test request (typically "Test_Request")
    test_request_value: Optional[int] = None  # Value to send for test request signal (typically 1)
    # Note: feedback_signal_source is already defined for Analog Static Test
    calib_state_signal: Optional[str] = None  # Signal name for calibration status (typically "PhaseOffset_Calib_Status")
    phase_v_offset_signal: Optional[str] = None  # Signal name for Phase V ADC offset (typically "PhaseV_ADC_Offset")
    phase_w_offset_signal: Optional[str] = None  # Signal name for Phase W ADC offset (typically "PhaseW_ADC_Offset")
    calibration_timeout_ms: Optional[int] = None  # Timeout in milliseconds to wait for CAL_DONE status (minimum 1000)
    
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
        elif self.type == 'Analog PWM Sensor':
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.feedback_pwm_frequency_signal:
                result['feedback_pwm_frequency_signal'] = self.feedback_pwm_frequency_signal
            if self.feedback_duty_signal:
                result['feedback_duty_signal'] = self.feedback_duty_signal
            if self.reference_pwm_frequency is not None:
                result['reference_pwm_frequency'] = self.reference_pwm_frequency
            if self.reference_duty is not None:
                result['reference_duty'] = self.reference_duty
            if self.pwm_frequency_tolerance is not None:
                result['pwm_frequency_tolerance'] = self.pwm_frequency_tolerance
            if self.duty_tolerance is not None:
                result['duty_tolerance'] = self.duty_tolerance
            if self.acquisition_time_ms is not None:
                result['acquisition_time_ms'] = self.acquisition_time_ms
        elif self.type == 'Fan Control Test':
            if self.fan_test_trigger_source is not None:
                result['fan_test_trigger_source'] = self.fan_test_trigger_source
            if self.fan_test_trigger_signal:
                result['fan_test_trigger_signal'] = self.fan_test_trigger_signal
            if self.fan_control_feedback_source is not None:
                result['fan_control_feedback_source'] = self.fan_control_feedback_source
            if self.fan_enabled_signal:
                result['fan_enabled_signal'] = self.fan_enabled_signal
            if self.fan_tach_feedback_signal:
                result['fan_tach_feedback_signal'] = self.fan_tach_feedback_signal
            if self.fan_fault_feedback_signal:
                result['fan_fault_feedback_signal'] = self.fan_fault_feedback_signal
            if self.dwell_time_ms is not None:
                result['dwell_time_ms'] = self.dwell_time_ms
            if self.test_timeout_ms is not None:
                result['test_timeout_ms'] = self.test_timeout_ms
        elif self.type == 'External 5V Test':
            if self.ext_5v_test_trigger_source is not None:
                result['ext_5v_test_trigger_source'] = self.ext_5v_test_trigger_source
            if self.ext_5v_test_trigger_signal:
                result['ext_5v_test_trigger_signal'] = self.ext_5v_test_trigger_signal
            if self.eol_ext_5v_measurement_source is not None:
                result['eol_ext_5v_measurement_source'] = self.eol_ext_5v_measurement_source
            if self.eol_ext_5v_measurement_signal:
                result['eol_ext_5v_measurement_signal'] = self.eol_ext_5v_measurement_signal
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.feedback_signal:
                result['feedback_signal'] = self.feedback_signal
            if self.tolerance_mv is not None:
                result['tolerance_mv'] = self.tolerance_mv
            if self.pre_dwell_time_ms is not None:
                result['pre_dwell_time_ms'] = self.pre_dwell_time_ms
            if self.dwell_time_ms is not None:
                result['dwell_time_ms'] = self.dwell_time_ms
        elif self.type == 'DC Bus Sensing':
            if self.oscilloscope_channel:
                result['oscilloscope_channel'] = self.oscilloscope_channel
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.feedback_signal:
                result['feedback_signal'] = self.feedback_signal
            if self.dwell_time_ms is not None:
                result['dwell_time_ms'] = self.dwell_time_ms
            if self.tolerance_v is not None:
                result['tolerance_v'] = self.tolerance_v
        elif self.type == 'Output Current Calibration':
            if self.test_trigger_source is not None:
                result['test_trigger_source'] = self.test_trigger_source
            if self.test_trigger_signal:
                result['test_trigger_signal'] = self.test_trigger_signal
            if self.test_trigger_signal_value is not None:
                result['test_trigger_signal_value'] = self.test_trigger_signal_value
            if self.current_setpoint_signal:
                result['current_setpoint_signal'] = self.current_setpoint_signal
            if self.output_current_trim_signal:
                result['output_current_trim_signal'] = self.output_current_trim_signal
            if self.initial_trim_value is not None:
                result['initial_trim_value'] = self.initial_trim_value
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.feedback_signal:
                result['feedback_signal'] = self.feedback_signal
            if self.oscilloscope_channel:
                result['oscilloscope_channel'] = self.oscilloscope_channel
            if self.oscilloscope_timebase:
                result['oscilloscope_timebase'] = self.oscilloscope_timebase
            if self.minimum_test_current is not None:
                result['minimum_test_current'] = self.minimum_test_current
            if self.maximum_test_current is not None:
                result['maximum_test_current'] = self.maximum_test_current
            if self.step_current is not None:
                result['step_current'] = self.step_current
            if self.pre_acquisition_time_ms is not None:
                result['pre_acquisition_time_ms'] = self.pre_acquisition_time_ms
            if self.acquisition_time_ms is not None:
                result['acquisition_time_ms'] = self.acquisition_time_ms
            if self.tolerance_percent is not None:
                result['tolerance_percent'] = self.tolerance_percent
        elif self.type == 'Charged HV Bus Test':
            if self.command_signal_source is not None:
                result['command_signal_source'] = self.command_signal_source
            if self.test_trigger_signal:
                result['test_trigger_signal'] = self.test_trigger_signal
            if self.test_trigger_signal_value is not None:
                result['test_trigger_signal_value'] = self.test_trigger_signal_value
            if self.set_output_current_trim_signal:
                result['set_output_current_trim_signal'] = self.set_output_current_trim_signal
            if self.fallback_output_current_trim_value is not None:
                result['fallback_output_current_trim_value'] = self.fallback_output_current_trim_value
            if self.set_output_current_setpoint_signal:
                result['set_output_current_setpoint_signal'] = self.set_output_current_setpoint_signal
            if self.output_test_current is not None:
                result['output_test_current'] = self.output_test_current
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.dut_test_state_signal:
                result['dut_test_state_signal'] = self.dut_test_state_signal
            if self.enable_relay_signal:
                result['enable_relay_signal'] = self.enable_relay_signal
            if self.enable_pfc_signal:
                result['enable_pfc_signal'] = self.enable_pfc_signal
            if self.pfc_power_good_signal:
                result['pfc_power_good_signal'] = self.pfc_power_good_signal
            if self.pcmc_signal:
                result['pcmc_signal'] = self.pcmc_signal
            if self.psfb_fault_signal:
                result['psfb_fault_signal'] = self.psfb_fault_signal
            if self.test_time_ms is not None:
                result['test_time_ms'] = self.test_time_ms
        elif self.type == 'Charger Functional Test':
            if self.command_signal_source is not None:
                result['command_signal_source'] = self.command_signal_source
            if self.test_trigger_signal:
                result['test_trigger_signal'] = self.test_trigger_signal
            if self.test_trigger_signal_value is not None:
                result['test_trigger_signal_value'] = self.test_trigger_signal_value
            if self.set_output_current_trim_signal:
                result['set_output_current_trim_signal'] = self.set_output_current_trim_signal
            if self.fallback_output_current_trim_value is not None:
                result['fallback_output_current_trim_value'] = self.fallback_output_current_trim_value
            if self.set_output_current_setpoint_signal:
                result['set_output_current_setpoint_signal'] = self.set_output_current_setpoint_signal
            if self.output_test_current is not None:
                result['output_test_current'] = self.output_test_current
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.dut_test_state_signal:
                result['dut_test_state_signal'] = self.dut_test_state_signal
            if self.enable_relay_signal:
                result['enable_relay_signal'] = self.enable_relay_signal
            if self.enable_pfc_signal:
                result['enable_pfc_signal'] = self.enable_pfc_signal
            if self.pfc_power_good_signal:
                result['pfc_power_good_signal'] = self.pfc_power_good_signal
            if self.pcmc_signal:
                result['pcmc_signal'] = self.pcmc_signal
            if self.output_current_signal:
                result['output_current_signal'] = self.output_current_signal
            if self.psfb_fault_signal:
                result['psfb_fault_signal'] = self.psfb_fault_signal
            if self.output_current_tolerance is not None:
                result['output_current_tolerance'] = self.output_current_tolerance
            if self.test_time_ms is not None:
                result['test_time_ms'] = self.test_time_ms
        elif self.type == 'Phase Offset Calibration Test':
            if self.test_request_source is not None:
                result['test_request_source'] = self.test_request_source
            if self.test_request_signal:
                result['test_request_signal'] = self.test_request_signal
            if self.test_request_value is not None:
                result['test_request_value'] = self.test_request_value
            if self.feedback_signal_source is not None:
                result['feedback_signal_source'] = self.feedback_signal_source
            if self.calib_state_signal:
                result['calib_state_signal'] = self.calib_state_signal
            if self.phase_v_offset_signal:
                result['phase_v_offset_signal'] = self.phase_v_offset_signal
            if self.phase_w_offset_signal:
                result['phase_w_offset_signal'] = self.phase_w_offset_signal
            if self.calibration_timeout_ms is not None:
                result['calibration_timeout_ms'] = self.calibration_timeout_ms
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
        test_mode: Test mode value (0-3, default 0) - DUT must be in this mode before test execution
    """
    name: str
    actuation: ActuationConfig
    feedback_signal: Optional[str] = None
    feedback_message_id: Optional[int] = None
    test_mode: int = 0  # Test mode: 0-3, default 0
    
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
        if self.test_mode is not None:
            result['test_mode'] = self.test_mode
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
            feedback_message_id=data.get('feedback_message_id'),
            test_mode=data.get('test_mode', 0)  # Default to 0 if not specified
        )

