# Test Type System Overview

## Purpose

This document provides a high-level overview of the test type system in the EOL Host Application. For detailed implementation instructions, see `ADDING_NEW_TEST_TYPES.md`. For quick reference, see `TEST_TYPE_QUICK_REFERENCE.md`.

## System Architecture

The test type system is a distributed architecture where test type definitions and logic are spread across multiple components:

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Type Definition                     │
│  ┌──────────────────┐  ┌────────────────────────────────┐ │
│  │  JSON Schema     │  │  Data Model                    │ │
│  │  (schema.json)   │  │  (test_profile.py)             │ │
│  └──────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                      │
│  ┌──────────────────┐  ┌────────────────────────────────┐ │
│  │  Create Dialog   │  │  Edit Dialog                   │ │
│  │  (base_gui.py)   │  │  (base_gui.py)                 │ │
│  └──────────────────┘  └────────────────────────────────┘ │
│  ┌──────────────────┐  ┌────────────────────────────────┐ │
│  │  Validation      │  │  Report Generation              │ │
│  │  (base_gui.py)   │  │  (base_gui.py)                 │ │
│  └──────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Execution Layer                           │
│  ┌──────────────────┐  ┌────────────────────────────────┐ │
│  │  Test Runner      │  │  Test Execution Service        │ │
│  │  (test_runner.py)│  │  (test_execution_service.py)   │ │
│  └──────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Current Test Types

The system currently supports 8 test types:

1. **Digital Logic Test** - Tests digital relay states (LOW→HIGH→LOW sequence)
2. **Analog Sweep Test** - Sweeps DAC voltages and monitors feedback signals
3. **Phase Current Test** - Phase current calibration with oscilloscope integration
4. **Analog Static Test** - Static analog measurement comparison (feedback vs EOL)
5. **Temperature Validation Test** - Temperature measurement validation against reference
6. **Fan Control Test** - Fan control system testing (enable, tach, fault monitoring)
7. **External 5V Test** - External 5V power supply testing (disabled/enabled phases)
8. **DC Bus Sensing** - DC bus voltage sensing with oscilloscope integration

## Data Flow

### Test Creation Flow

```
User selects test type
    ↓
GUI creates type-specific widget
    ↓
User fills in configuration fields
    ↓
GUI builds actuation dictionary
    ↓
Validation checks required fields
    ↓
Test saved to JSON file
```

### Test Execution Flow

```
Test loaded from JSON
    ↓
TestRunner.run_test() called
    ↓
Test type determined from actuation.type
    ↓
Type-specific execution branch runs
    ↓
Results returned (success, info)
    ↓
Results displayed in GUI and reports
```

## Key Components

### 1. Schema Definition (`backend/data/tests/schema.json`)

- Defines valid test type names in `enum`
- Defines required/optional fields for each test type in `oneOf`
- Used for JSON validation when loading test files

### 2. Data Model (`host_gui/models/test_profile.py`)

- `ActuationConfig` dataclass defines all possible test configuration fields
- Fields are optional to support different test types
- Documents each test type's field usage

### 3. GUI Components (`host_gui/base_gui.py`)

- **Create Dialog** (`_on_create_test()`): Allows users to create new tests
- **Edit Dialog** (`_on_edit_test()`): Allows users to edit existing tests
- **Validation** (`_validate_test()`): Validates test configuration before saving
- **Reports** (`_build_test_report()`, `_refresh_test_report()`): Generates test reports

### 4. Execution Engine (`host_gui/test_runner.py`)

- `TestRunner.run_test()`: Main execution method
- Contains type-specific execution branches
- Handles CAN communication, signal reading, data collection
- Returns pass/fail results

### 5. Service Layer (`host_gui/services/test_execution_service.py`)

- Decoupled test execution (no GUI dependencies)
- Similar structure to TestRunner
- Used for headless/automated execution

## Test Type Characteristics

### Simple Test Types
- **Digital Logic Test**: Send command → wait → verify feedback
- **Temperature Validation Test**: Read signal → compare to reference

### Complex Test Types
- **Analog Sweep Test**: Multi-step voltage sweep with MUX control
- **Phase Current Test**: State machine with oscilloscope integration
- **External 5V Test**: Multi-phase test (disabled/enabled states)

### Common Patterns

1. **Signal Reading Pattern**: Read signal during dwell time → calculate average → compare to reference
2. **Command + Feedback Pattern**: Send command → wait → verify feedback matches expected
3. **Multi-Phase Pattern**: Execute multiple phases → evaluate each → combine results

## DBC Integration

The system supports two modes:

1. **DBC Mode** (DBC file loaded):
   - Dropdown menus for CAN messages and signals
   - Automatic message encoding/decoding
   - Signal validation

2. **Non-DBC Mode** (no DBC file):
   - Free-text inputs for CAN IDs and signal names
   - Manual configuration
   - Less validation

Most test types support both modes, with the GUI adapting the input method based on DBC availability.

## Validation Strategy

### Schema Validation
- JSON schema validates structure and types
- Enforces required fields
- Validates value ranges (min/max)

### Application Validation
- `_validate_test()` performs additional checks:
  - Test name uniqueness
  - Test type validity
  - Required fields presence
  - Field value constraints (ranges, non-negative, etc.)
  - Actuation type matches test type

## Execution Strategy

### Test Execution Steps

1. **Parameter Extraction**: Read configuration from actuation dictionary
2. **Parameter Validation**: Check required fields and constraints
3. **Test Execution**: 
   - Send actuation commands (if needed)
   - Wait for stabilization (pre-dwell)
   - Collect data during dwell time
   - Process data (averages, comparisons, etc.)
4. **Result Determination**: Calculate pass/fail based on criteria
5. **Result Return**: Return (success: bool, info: str)

### Error Handling

- All execution branches wrapped in try/except
- Meaningful error messages returned
- Logging for debugging
- Graceful degradation (fallback values, default behaviors)

## Extension Points

To add a new test type, you must modify:

1. **Schema** - Add enum entry and oneOf definition
2. **Data Model** - Document fields (add new fields if needed)
3. **Create Dialog** - Add UI for configuration
4. **Edit Dialog** - Add UI for editing
5. **Validation** - Add type check and field validation
6. **Execution** - Implement test logic
7. **Reports** - Add to filters and display logic

See `ADDING_NEW_TEST_TYPES.md` for detailed instructions.

## Best Practices

1. **Consistency**: Use exact same test type name everywhere
2. **Validation**: Always validate required fields and constraints
3. **Error Handling**: Provide meaningful error messages
4. **Logging**: Log important events and errors
5. **Non-Blocking**: Use `_nb_sleep()` instead of `time.sleep()`
6. **DBC Support**: Support both DBC and non-DBC modes
7. **Testing**: Test with valid and invalid configurations
8. **Documentation**: Document all fields and their purposes

## Common Issues

1. **Type Name Mismatch**: Test type name must match exactly in all files
2. **Missing Validation**: Forgetting to validate required fields
3. **Blocking Sleep**: Using `time.sleep()` freezes UI
4. **Incomplete Implementation**: Missing execution branch or validation
5. **DBC Mode Only**: Not supporting non-DBC mode

## Related Files

- **Full Guide**: `docs/ADDING_NEW_TEST_TYPES.md`
- **Quick Reference**: `docs/TEST_TYPE_QUICK_REFERENCE.md`
- **Schema**: `backend/data/tests/schema.json`
- **Data Model**: `host_gui/models/test_profile.py`
- **GUI**: `host_gui/base_gui.py`
- **Execution**: `host_gui/test_runner.py`
- **Service**: `host_gui/services/test_execution_service.py`

## Summary

The test type system is designed to be extensible but requires coordinated changes across multiple files. The architecture separates concerns (schema, UI, validation, execution) while maintaining consistency through shared test type names and data structures. When adding a new test type, follow the systematic approach outlined in the detailed documentation to ensure all components are updated correctly.

