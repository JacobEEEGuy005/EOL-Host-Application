# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `[Enter exact test type name, e.g., "Voltage Regulation Test"]`
- **Short Description**: `[One-line description of what this test does]`
- **Detailed Description**: 
  ```
  [Provide a detailed description of the test type, including:
   - What it tests
   - How it works
   - What hardware/equipment it requires
   - Any special considerations]
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `field_name_1` | `integer` | `Description of field` | `Range: 0-65535, Required` | `1234` |
| `field_name_2` | `string` | `Description of field` | `Non-empty, Required` | `"SignalName"` |
| `field_name_3` | `number` | `Description of field` | `Minimum: 0, Required` | `5.5` |

### Optional Fields
List all optional fields:

| Field Name | Type | Description | Validation Rules | Default Value |
|------------|------|-------------|------------------|---------------|
| `optional_field_1` | `integer` | `Description` | `Range: 1-10000` | `1000` |
| `optional_field_2` | `string` | `Description` | `Max length: 50` | `""` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (if sending commands):
  - Message ID: `[CAN ID, e.g., 0x123]`
  - Signals used: `[List signal names]`
  - Purpose: `[What commands are sent]`

- **Feedback Messages** (if reading feedback):
  - Message ID: `[CAN ID]`
  - Signals used: `[List signal names]`
  - Purpose: `[What data is read]`

- **DBC Support**: `[Yes/No - Can this test work with DBC file loaded?]`
- **Non-DBC Support**: `[Yes/No - Can this test work without DBC file?]`

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. [Step 1 description]
   - Action: [What happens]
   - Duration: [How long, if applicable]
   - Expected result: [What should happen]

2. [Step 2 description]
   - Action: [What happens]
   - Duration: [How long, if applicable]
   - Expected result: [What should happen]

3. [Continue for all steps...]
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `[Clear condition for passing, e.g., "Average value within tolerance"]`
- **Fail Condition**: `[Clear condition for failing, e.g., "Average value exceeds tolerance"]`
- **Calculation Method**: `[How to calculate the result, e.g., "Calculate average of collected values, compare to reference"]`

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: `[List all signals that need to be read]`
- **Collection Duration**: `[How long to collect data, e.g., "dwell_time_ms milliseconds"]`
- **Sampling Rate**: `[How often to sample, if applicable]`
- **Data Processing**: `[What processing is needed, e.g., "Calculate average", "Find min/max"]`

### Timing Requirements
Specify any timing requirements:

- **Pre-Dwell Time**: `[Time to wait before data collection, if needed]`
- **Dwell Time**: `[Time to collect data]`
- **Post-Dwell Time**: `[Time to wait after data collection, if needed]`
- **Total Duration**: `[Estimated total test duration]`

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: `[Field Label]`
- **Type**: `[QLineEdit/QComboBox/QSpinBox/QDoubleSpinBox]`
- **Placeholder**: `[Example value or hint]`
- **Validator**: `[If applicable, e.g., "Integer 0-10000"]`
- **DBC Mode**: `[Dropdown/Free-text/Both]`
- **Required**: `[Yes/No]`

#### Field 2: `[Field Label]`
- **Type**: `[Widget type]`
- **Placeholder**: `[Example]`
- **Validator**: `[If applicable]`
- **DBC Mode**: `[Dropdown/Free-text/Both]`
- **Required**: `[Yes/No]`

[Continue for all fields...]

### Feedback Fields Visibility
- **Show Feedback Fields**: `[Yes/No - Does this test use the general feedback fields?]`
- **Custom Feedback Fields**: `[Yes/No - Does this test have its own feedback fields?]`

### Plot Requirements
- **Needs Plot**: `[Yes/No]`
- **Plot Type**: `[X-Y plot/Time series/Other]`
- **X-Axis**: `[What to plot on X-axis]`
- **Y-Axis**: `[What to plot on Y-axis]`
- **Update Frequency**: `[How often to update plot during execution]`

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "type": {"const": "[Test Type Name]"},
  "required_field_1": {"type": "integer", "minimum": 0, "maximum": 65535},
  "required_field_2": {"type": "string"},
  "optional_field_1": {"type": "number", "minimum": 0},
  "dwell_time_ms": {"type": "integer", "minimum": 1}
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [ ] Test type is in allowed list
- [ ] Actuation type matches test type
- [ ] `required_field_1` is present and in valid range
- [ ] `required_field_2` is present and non-empty
- [ ] `optional_field_1` is non-negative (if provided)
- [ ] `dwell_time_ms` is positive (if applicable)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required field: field_name"`
   - Handling: Return `False, "Missing required field: field_name"`

2. **Invalid Field Value**
   - Error: `"Field value out of range"`
   - Handling: Return `False, "Field value out of range: expected 0-100, got {value}"`

3. **Signal Not Found**
   - Error: `"Signal not found during execution"`
   - Handling: Return `False, "No data collected: signal not found"`

[Continue for all error scenarios...]

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Example Test 1",
  "type": "[Test Type Name]",
  "actuation": {
    "type": "[Test Type Name]",
    "required_field_1": 1234,
    "required_field_2": "SignalName",
    "optional_field_1": 5.5,
    "dwell_time_ms": 1000
  }
}
```

### Example 2: Full Configuration
```json
{
  "name": "Example Test 2",
  "type": "[Test Type Name]",
  "actuation": {
    "type": "[Test Type Name]",
    "required_field_1": 5678,
    "required_field_2": "AnotherSignal",
    "optional_field_1": 10.0,
    "optional_field_2": "Additional info",
    "dwell_time_ms": 2000
  }
}
```

## Implementation Notes

### Special Considerations
- `[Any special implementation notes, e.g., "Requires oscilloscope integration", "Needs state machine", "Multi-phase test"]`

### Dependencies
- `[List any special dependencies, e.g., "Requires oscilloscope_service", "Needs phase_current_service"]`

### Similar Test Types
- `[List similar existing test types that can be used as reference, e.g., "Similar to Temperature Validation Test", "Follows Analog Static Test pattern"]`

### Testing Requirements
- `[Any special testing requirements, e.g., "Test with hardware connected", "Requires specific DBC file"]`

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `[Name of similar test type, e.g., "Temperature Validation Test"]`
- **Why Similar**: `[Explain why this is a good reference]`
- **Key Differences**: `[What's different from the reference]`

### Code Patterns to Use
- `[List specific patterns, e.g., "Use signal reading pattern", "Use multi-phase pattern", "Use CAN command + feedback pattern"]`

## Acceptance Criteria

### Functional Requirements
- [ ] Test type appears in create test dialog dropdown
- [ ] Test type appears in edit test dialog dropdown
- [ ] All configuration fields are displayed correctly
- [ ] Test can be created and saved successfully
- [ ] Test can be edited and saved successfully
- [ ] Validation works correctly (rejects invalid configurations)
- [ ] Test execution runs without errors
- [ ] Test execution returns correct pass/fail results
- [ ] Test results appear in results table
- [ ] Test results appear in test report
- [ ] JSON schema validation works

### Technical Requirements
- [ ] All files updated according to documentation
- [ ] Code follows existing patterns and style
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Non-blocking sleep used (no `time.sleep()`)
- [ ] DBC mode supported (if applicable)
- [ ] Non-DBC mode supported (if applicable)

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded (if applicable)
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully

---

## Instructions for AI Agent

Please implement this new test type following the documentation in:
- `docs/ADDING_NEW_TEST_TYPES.md` - Full implementation guide
- `docs/TEST_TYPE_QUICK_REFERENCE.md` - Quick reference
- `docs/TEST_TYPE_SYSTEM_OVERVIEW.md` - System overview

### Implementation Steps
1. Review the test type requirements above
2. Follow the step-by-step guide in `ADDING_NEW_TEST_TYPES.md`
3. Update all required files:
   - `backend/data/tests/schema.json`
   - `host_gui/models/test_profile.py`
   - `host_gui/base_gui.py` (multiple methods)
   - `host_gui/test_runner.py`
   - `host_gui/services/test_execution_service.py` (optional)
4. Implement validation logic
5. Implement execution logic
6. Test thoroughly with both valid and invalid configurations
7. Ensure all acceptance criteria are met

### Key Reminders
- Use exact test type name consistently across all files
- Support both DBC and non-DBC modes (if applicable)
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style

