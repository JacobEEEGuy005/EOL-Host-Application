# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Phase Offset Calibration Test`
- **Short Description**: `Puts IPD DUT in Drive Mode, runs phase offset calibration, and reads Phase V/W ADC offsets when CAL_DONE`
- **Detailed Description**: 
  ```
  This test triggers phase offset calibration on the IPD DUT and validates completion by:
  1. Sending Test Request = 1 (Drive Mode) on the command message (e.g. MessageType 32 on message 272)
  2. Polling the feedback message for PhaseOffset_Calib_Status until value = 2 (CAL_DONE) or timeout
  3. If CAL_DONE within the configured timeout (e.g. 5 s): read PhaseV_ADC_Offset and PhaseW_ADC_Offset
  4. If CAL_DONE not reached within timeout: FAIL
  
  DBC Reference (eol_firmware.dbc):
  - Command: BO_ 272, Test_Request m32, value 1 = Drive Mode
  - Feedback: BO_ 250, MessageType 122: PhaseOffset_Calib_Status (0=INIT, 1=CAL, 2=CAL_DONE), PhaseV_ADC_Offset, PhaseW_ADC_Offset
  
  Result includes calibration result and calibration values (Phase V Offset, Phase W Offset).
  ```

## Test Configuration Fields

### Required Fields

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `test_request_source` | `integer` | CAN message ID for Test Request command | Required | `272` |
| `test_request_signal` | `string` | Signal name for Test Request (e.g. Test_Request) | Non-empty | `"Test_Request"` |
| `test_request_value` | `integer` | Value to send (1 = Drive Mode) | 0–255 | `1` |
| `feedback_signal_source` | `integer` | CAN message ID for feedback (e.g. 250) | Required | `250` |
| `calib_state_signal` | `string` | Signal name for calibration state (e.g. PhaseOffset_Calib_Status) | Non-empty | `"PhaseOffset_Calib_Status"` |
| `phase_v_offset_signal` | `string` | Signal name for Phase V ADC offset | Non-empty | `"PhaseV_ADC_Offset"` |
| `phase_w_offset_signal` | `string` | Signal name for Phase W ADC offset | Non-empty | `"PhaseW_ADC_Offset"` |
| `calibration_timeout_ms` | `integer` | Timeout in ms from Test Request sent (e.g. 5000) | Min 1000 | `5000` |

### CAN Message/Signal Fields

- **Command Message**: `test_request_source` (e.g. 272)
  - Signals: `test_request_signal` = `test_request_value` (1), DeviceID, MessageType (32)
- **Feedback Message**: `feedback_signal_source` (e.g. 250, MessageType 122)
  - Signals: `calib_state_signal` (poll until 2 = CAL_DONE), `phase_v_offset_signal`, `phase_w_offset_signal`

## Execution Flow

1. Encode and send Test Request = 1 on command message.
2. Poll feedback message for `calib_state_signal` until value == 2 (CAL_DONE) or `calibration_timeout_ms` elapsed.
3. If CAL_DONE in time: read `phase_v_offset_signal` and `phase_w_offset_signal`; PASS with result string including both values.
4. If timeout: FAIL with message indicating calibration timeout.

## Implementation References

- Schema: `backend/data/tests/schema.json` (type enum + oneOf for Phase Offset Calibration Test)
- Model: `host_gui/models/test_profile.py` (ActuationConfig)
- GUI: `host_gui/base_gui.py` (create/edit widgets, validation, report filter)
- Execution: `host_gui/test_runner.py` (`run_single_test` branch for `Phase Offset Calibration Test`)
