# End-of-Line (EOL) Host Application - Project Requirements

**Project Name:** EOL Testing Application for Integrated Power Converter (IPC)  
**Version:** 1.0  
**Date:** October 2025  
**Organization:** Ergon Mobility Pvt Ltd  
**Platform:** Linux,Windows  

---

## 1. Executive Summary

### 1.1 Project Overview
The End-of-Line (EOL) Host Application is designed to control the EOL Hardware via a CAN Bus. It commands the EOL Hardware to apply voltages to digital inputs or apply a controlled voltage to analog inputs of the IPC. The IPC is put to Test/Calibration mode, where it transmits state of the digital inputs and the analog voltages on the same CAN Bus. The EOL Host application automates this process and generates a test and calibration report for each IPC.

### 1.2 Project Goals
- Automate end-of-line testing procedures to reduce manual testing time by 90%
- Ensure 100% signal integrity validation before IPC deployment
- Provide real-time visual feedback and comprehensive test reporting
- Support extensible test configurations without code modifications

### 1.3 Target Users
- Quality Assurance Engineers
- Production Line Technicians
- Test Engineers
- Hardware Validation Teams

---

## 2. Functional Requirements

### 2.1 Digital Signal Testing

#### 2.1.1 Relay Control
**REQ-DST-001:** The system shall control up to 4 relays through CAN Protocol
- R0: Key Switch relay
- R1: Reverse relay
- R2: Boost relay
- R3: Forward relay

**REQ-DST-002:** System shall initialize all relays to OFF state on startup via CAN.  
**REQ-DST-003:** System shall implement 100ms debounce delay after relay state changes (configurable via parameters.json)

#### 2.1.2 Digital Test Execution
**REQ-DST-004:** System shall execute ON/OFF test for each Digital signal
1. Turn on the relay 
2. Wait for stabilization (100ms)
3. Read CAN feedback from EOL Hardware
4. Read the CAN feedback from IPC
5. Turn off the relay
6. Read CAN feedback from EOL Hardware
7. Read the CAN feedback from IPC

**REQ-DST-005:** System shall mark test as PASS if CAN feedback matches expected value for ON and OFF.

**REQ-DST-006:** System shall mark test as FAIL if:
- No CAN feedback received within 500ms timeout
- CAN feedback value doesn't match expected byte value for ON or OFF

**Normalization Note:** Use a single canonical timeout constant (default: 500 ms). All timeout references (previously 300-500ms or 500ms) shall reference this constant and be configurable in parameters.json as `can_feedback_timeout_ms`.

### 2.2 Analog Signal Testing

#### 2.2.1 DAC/MUX Control
**REQ-AST-001:** System shall control the DAC on the EOL Hardware, capable of 0-5000mV output via CAN. 

**REQ-AST-002:** System shall control 8-channel analog multiplexer via CAN which will apply DAC voltage to IPC Analog Input.

**REQ-AST-003:** System shall supports voltage output range 0-5V.

**REQ-AST-004:** System shall enable the MUX, set MUX to channel 0 by default and reset after each test

#### 2.2.2 Voltage Sweep Testing
**REQ-AST-005:** System shall perform voltage sweep test for analog signals:
1. Set MUX to signal-specific channel (0-7)
2. Sweep DAC voltage from 0V to 5V in 100mV steps
3. For each voltage step:
   - Apply voltage via DAC
   - Wait 200ms for stabilization
   - Read CAN feedback from EOL Hardware
   - Read the CAN feedback from IPC
   - Record all three values (applied, CAN EOL ADC, CAN IPC ADC)

**REQ-AST-006:** System shall mark analog test as PASS if all voltage steps meet tolerance: default tolerance = ±10 mV (0.01 V). Acceptance criteria in testing sections updated to match ±10 mV.

**REQ-AST-007:** System shall generate live plot during voltage sweep showing:
- X-axis: Applied EOL DAC voltage
- Y-axis: Feedback voltage from IPC
- Two lines: IPC CAN feedback (solid) and EOL ADC feedback (dashed)

#### 2.2.3 ADC Verification
**REQ-AST-008:** System shall read following voltages from EOL ADC:
- EOL ADC A0 : 5V Rail Voltage
- EOL ADC A1 : EOL DAC Output Voltage

**REQ-AST-009:** System shall display both voltage in real-time on UI

### 2.3 CAN Bus Communication

#### 2.3.1 CAN Interface Support
**REQ-CAN-001:** System shall support two CAN interface types:
1. CANalyst-II (USB-CAN-B) via `canalystii` driver
2. PEAK CAN via SocketCAN (`can0` interface)
3. CL2000 using python-can-csscan-serial 

**REQ-CAN-002:** System shall auto-detect and connect to available CAN interface on startup

**REQ-CAN-003:** System shall use 500kbps bitrate for all CAN communications

**REQ-CAN-004:** System shall automatically bring up `can0` interface if using SocketCAN

#### 2.3.2 CAN Message Handling
**REQ-CAN-005:** System shall run CAN listener in background daemon thread

**REQ-CAN-006:** System shall buffer last 100 CAN messages in thread-safe deque

**REQ-CAN-007:** System shall implement timestamp-based message freshness checking:
- Only process CAN messages received AFTER test action
- Compare message timestamp against initial snapshot

**REQ-CAN-008:** System shall poll for CAN feedback with configurable timeout (default 300-500ms)

**REQ-CAN-009:** System shall detect CAN disconnection and attempt automatic reconnection

**REQ-CAN-010:** System shall display real-time CAN connection status with visual indicator:
- Green: Connected and active
- Red (blinking): Disconnected

#### 2.3.3 CAN Message Format
**REQ-CAN-011:** CAN DBC for EOL Hardware will be provided, which is to be used link Host with EOL Hardware 

**REQ-CAN-012:** CAN DBC for IPC will be provided, which will link the digital and analog feedback.

### 2.4 Configuration Management

#### 2.4.1 JSON Configuration File
**REQ-CFG-001:** System shall load all test definitions from `parameters.json`

**REQ-CFG-002:** Configuration file shall define signals with structure
- The AI Agent shall shall propose a json structure based on new requriements for the developer to choose

**REQ-CFG-003:** System shall support adding new signals via JSON without code changes

**REQ-CFG-004:** System shall support configuring the json in the GUI

**REQ-CFG-004:** The JSON shall link the EOL test hardware to the signal under test from IPC, using CAN dbc file from both EOL and IPC

**REQ-CFG-005:** System shall validate JSON schema on load and display errors for invalid configuration

**REQ-CFG-006:** Add a versioned JSON schema and example entry (suggested fields)

### 2.5 User Interface Requirements

#### 2.5.1 Application Navigation
**REQ-UI-001:** System shall display welcome screen on startup with:
- Ergon Mobility branding (`ergon.jpg` background)
- "Get Started" button to launch main test interface
- "Test Configurator" button to launch GUI based windows to configure the json

**REQ-UI-002:** System shall transition from welcome to main UI without blocking

**REQ-UI-003:** Application shall run in maximized window mode by default

#### 2.5.2 Test Configurator
**REQ-UI-004:** System shall support selecting the dbc files for EOL Hardware and for the IPC
**REQ-UI-005:** System shall support link the Signal under test from IPC CAN dbc and link it to the which Hardware test from EOL CAN dbc
**REQ-UI-006:** System shall support on creating, saving, loading json file.
**REQ-UI-007:** System will check the test configuration before saving as json.

#### 2.5.2 Main Test Interface
**REQ-UI-008:** Main interface shall display:
- Application title "CAN Signal Test Runner"
- CAN connection status (visual dot + text label)
- The EOL 5V Rail voltage and the DAC Output (updated every 1 second)
- Control buttons: Run Tests, Export Report, Send CAN Frame, Relay Control
- Progress label showing test status
- Results list with color-coded PASS (green) / FAIL (red)
- Footer with copyright notice

**REQ-UI-009:** Run Tests button shall:
- Disable itself during test execution
- Open live plot window for analog tests
- Open live log window showing console output
- Enable after test completion

**REQ-UI-010:** Results list shall display format: `Signal Name (category) - STATUS`

**REQ-UI-011:** Double-clicking result item shall open detailed test dialog

#### 2.5.3 Test Detail Dialog
**REQ-UI-012:** Detail dialog shall display:
- Signal name, category, and overall status
- Per-test results with pass/fail indicators
- For analog tests: textual sweep results table
- For analog tests: matplotlib graph (applied vs feedback voltage)
- Close button

**REQ-UI-013:** Sweep results table shall show:
- Applied voltage from EOL Hardware → CAN feedback voltage from IPC (error) ✅/❌
- ADC feedback voltage
- Error tolerance checking

#### 2.5.4 Live Plotting
**REQ-UI-014:** Live plot window shall:
- Update in real-time during voltage sweep
- Display separate lines for Analog Signal 1 (blue) and Analog Signal 2 (green)
- Show both CAN feedback (solid line) and ADC voltage (dashed line)
- Auto-scale axes for optimal viewing
- Include grid and legend

**REQ-UI-015:** Plot shall emit Qt signals for thread-safe updates from test runner

#### 2.5.5 Manual Controls
**REQ-UI-016:** Relay Control dialog shall provide:
- Manual ON/OFF buttons for each of 4 relays
- Styled buttons matching application theme (#005792 blue)
- Manual controls shall issue CAN control frames to the EOL Hardware (STM32); the Host will not perform local GPIO actuation

**REQ-UI-017:** Manual controls shall be disabled when the CAN link to the EOL Hardware is disconnected; queued commands are not sent when disconnected

#### 2.5.6 Test Logs
**REQ-UI-018:** Log window shall:
- Redirect stdout/stderr to scrollable text area
- Auto-scroll to latest output
- Display during test execution
- Stop logging redirection after test completion

### 2.6 Report Generation

**REQ-RPT-001:** System shall support export of test results to:
- Plain text (.txt)
- CSV format (.csv)

**REQ-RPT-002:** Report shall include for each signal:
- Signal name and category
- Overall status (PASS/FAIL)
- Per-test results with values
- Voltage sweep data for analog tests

**REQ-RPT-003:** Export button shall be disabled if no test results available

### 2.7 Error Handling & Recovery

**REQ-ERR-001:** System shall gracefully handle missing hardware:
- No heartbeat from EOL Hardware
- Decode error status of EOL Hardware from CAN
- Disable analog tests if DAC unavailable on the EOL Hardware

**REQ-ERR-002:** System shall display error dialog for critical failures:
- CAN bus initialization failure
- Any Error from EOL Hardware
- Any Error from IPC 

**REQ-ERR-003:** System shall implement test abortion:
- User can close live plot or log window to stop tests
- Stop button/signal shall propagate to test thread
- All hardware shall return to safe state on abort

**REQ-ERR-004:** System shall reset hardware to safe state on:
- Test completion (success or failure)
- Application exit
- Test abortion
- Error conditions

Safe state defined as:
- All relays OFF
- MUX set to channel 0
- DAC set to 0V

---

## 3. Non-Functional Requirements

### 3.1 Performance

**REQ-NFR-001:** Test execution shall complete for all signals within 2 minutes.( This can be relaxed depending on the amount test and duration of each test)

**REQ-NFR-002:** UI shall remain responsive during tests (no blocking operations on main thread)

**REQ-NFR-003:** CAN message polling shall have <50ms latency

**REQ-NFR-004:** Analog voltage sweep shall complete in <30 seconds per signal.

**REQ-NFR-005:** Live plot updates shall occur at minimum 10 FPS

### 3.2 Reliability

**REQ-NFR-006:** System shall handle 1000+ consecutive test runs without memory leaks

**REQ-NFR-007:** CAN reconnection shall succeed within 3 attempts or 5 seconds

**REQ-NFR-008:** Thread-safe operations shall prevent race conditions in CAN message buffer

### 3.3 Usability

**REQ-NFR-009:** Application startup shall complete within 5 seconds on supported host platforms (Raspberry Pi 5 when used)

**REQ-NFR-010:** UI controls shall have clear visual feedback on hover/click

**REQ-NFR-011:** Error messages shall be user-friendly and actionable

**REQ-NFR-012:** Test results shall be easily interpretable (color-coded, clear labels)

### 3.4 Maintainability

**REQ-NFR-013:** Code shall follow Python PEP 8 style guidelines

**REQ-NFR-014:** Test logic shall be decoupled from UI layer

**REQ-NFR-015:** Hardware controllers shall use abstraction pattern for easy replacement

**REQ-NFR-016:** Configuration changes shall not require code modifications

### 3.5 Portability

**REQ-NFR-017:** Application shall run on Linux (Raspberry Pi OS is supported) and Windows where CAN backends are available

**REQ-NFR-018:** Dependencies shall be installable via pip (requirements.txt)

**REQ-NFR-019:** Hardware addresses and pin mappings shall be configurable constants

### 3.6 Security

**REQ-NFR-021:** Access to CAN devices or drivers may require elevated permissions or vendor drivers (documented). The Host application itself does not perform direct GPIO or I2C operations on the EOL test harness — those are performed by the EOL Hardware (STM32).

**REQ-NFR-023:** CAN bus operations shall not interfere with other vehicle systems

---

## 4. Hardware Requirements

### 4.1 Computing Platform

**REQ-HW-001:** Host platform: Linux-based system (Raspberry Pi 5 recommended for on-site use) or Windows with supported CAN drivers

**REQ-HW-002:** Recommended OS: Raspberry Pi OS (Bookworm) for Raspberry Pi hosts; Linux distributions or Windows supported when appropriate CAN drivers are installed

**REQ-HW-003:** Python 3.11+ interpreter for host applications

### 4.2 EOL Hardware

**REQ-HW-004:** EOL Hardware has 4 relay control outputs 

**REQ-HW-005:** 0-5V DAC Output connected to selectable 8 Channel Analog Mux

**REQ-HW-006:** The 8 Channel Analog Mux can be enabled or disabled via CAN

**REQ-HW-007:** EOL Hardware has 4 Channel ADC
- A0 - Connected to 5V Rail
- A1 - Connected to DAC Output 

### 4.4 CAN Interface

**REQ-HW-008:** One of:
- CANalyst-II (USB-CAN-B) USB interface
- PEAK CAN USB interface with SocketCAN driver
- CL2000

**REQ-HW-009:** CAN bus must be properly terminated (120Ω)

**REQ-HW-010:** CAN bitrate must match ECU/IPC (500kbps)


### 4.6 Test Target (IPC/ECU)

**REQ-HW-011:** IPC must accept relay signals and respond via CAN

**REQ-HW-012:** IPC must accept analog voltage inputs (0-5V range)

**REQ-HW-013:** IPC must transmit feedback on specified CAN IDs

---

## 5. Software Dependencies
- AI Agent to update software dependancies based on new reuirements

### 5.1 Core Framework

**REQ-SW-001:** PyQt5 == 5.15.9 (GUI framework)

**REQ-SW-002:** The Host application shall not require `RPi.GPIO` or direct I2C libraries for hardware actuation — hardware actuation is performed by the EOL Hardware (STM32) over CAN. The Host requires CAN backends (see Communication Libraries).

### 5.2 Communication Libraries

**REQ-SW-003:** python-can == 4.5.0 (CAN bus abstraction)

**REQ-SW-004:** canalystii == 0.1 (CANalyst-II driver)

### 5.4 Visualization

**REQ-SW-005:** matplotlib == 3.10.3 (real-time plotting)

**REQ-SW-006:** numpy == 1.24.2 (numerical operations)

### 5.5 System Tools

**REQ-SW-007:** can-utils (for SocketCAN debugging)

---

## 6. System Architecture
- AI Agent to update System Architecture to suit new requirements.

### 6.1 Application Layers

```
┌─────────────────────────────────────┐
│     Presentation Layer (PyQt5)      │
│  main.py, can_test_ui.py            │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│       Business Logic Layer          │
│  test_runner.py, parameters.json    │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│     Hardware Abstraction Layer      │
│  can_adapter.py (Host CAN command   │
│  serializers), CAN drivers          │
│  EOL Hardware (STM32) handles GPIO, │
│  I2C, ADC/DAC, MUX and relay drive  │
└─────────────────────────────────────┘
```

### 6.2 Threading Model

**REQ-ARCH-001:** Main thread handles UI events and rendering

**REQ-ARCH-002:** TestRunnerThread executes tests without blocking UI

**REQ-ARCH-003:** CAN listener daemon thread receives messages continuously

**REQ-ARCH-004:** Qt signals/slots provide thread-safe communication

### 6.3 State Management

**REQ-ARCH-005:** Hardware state is encapsulated in controller classes

**REQ-ARCH-006:** Test results stored in list of dictionaries

**REQ-ARCH-007:** CAN messages buffered in thread-safe deque (max 100)

---

## 7. Testing & Validation
- AI Agent shall update and propose unit test required or to be removed

### 7.1 Unit Testing

**REQ-TST-001:** DAC voltage conversion logic shall be unit tested

**REQ-TST-002:** CAN message parsing shall be unit tested

**REQ-TST-003:** MUX channel selection shall be unit tested

### 7.2 Integration Testing

**REQ-TST-004:** Full relay test cycle shall be validated with oscilloscope

**REQ-TST-005:** Analog sweep accuracy shall be verified with multimeter

**REQ-TST-006:** CAN feedback timing shall be measured and logged

### 7.3 System Testing

**REQ-TST-007:** Complete test suite shall run on production hardware

**REQ-TST-008:** 100 consecutive test runs shall complete without errors

**REQ-TST-009:** CAN disconnection/reconnection scenarios shall be tested

### 7.4 Acceptance Criteria

**REQ-TST-010:** All relay tests shall pass with known-good IPC

**REQ-TST-011:** Analog tests shall achieve <0.1V error across full range

**REQ-TST-012:** Application shall start and complete tests in under 3 minutes

---

## 8. Deployment Requirements
- AI Agent shall update Deployment requirements

### 8.1 Installation

**REQ-DEP-001:** Installation shall be achievable via:
```bash
git clone <repository>
cd EndOfLine-Testing
pip install -r requirements.txt
```

**REQ-DEP-002:** Virtual environment usage shall be documented but optional

### 8.2 Configuration

**REQ-DEP-003:** Logo image (`ergon.jpg`) must be present in project root

**REQ-DEP-004:** `parameters.json` must be present and valid

### 8.3 Execution

**REQ-DEP-007:** Application shall start via: `python3 main.py`

**REQ-DEP-008:** Application shall handle Ctrl+C gracefully with cleanup

**REQ-DEP-009:** Application closing shall cleanup CAN resources

---

## 9. Future Enhancements (Out of Scope for v1.0)
- AI Agent shall ignore this section

### 9.1 Potential Features
- Database storage of test history
- Multi-IPC testing (parallel test stations)
- Remote monitoring dashboard
- Automated test report email
- Barcode/serial number scanning
- Pass/fail statistics and trending
- Test template management UI
- OTA firmware update for test procedure changes
- Support for additional CAN interfaces (e.g., Kvaser)
- Python logging framework integration

### 9.2 Hardware Expansions
- Support for multiple DACs (parallel analog testing)
- Digital input validation (read-back from IPC)
- PWM signal testing
- Temperature sensor integration
- Automated cable connection detection

---

## 10. Constraints & Assumptions

### 10.1 Constraints
- Single DAC limits analog tests to sequential execution
- Hardware-level GPIO signaling levels and I2C bus configuration are the responsibility of the EOL Hardware (STM32). The Host assumes the EOL Hardware enforces correct voltage levels and pull-ups.
- CAN bus shared with other systems (non-intrusive testing only)

### 10.2 Assumptions
- IPC/ECU firmware provides expected CAN feedback
- Test environment has stable power supply
- Hardware connections are verified before testing
- Operator has basic Linux knowledge (Raspberry Pi specifics documented where applicable)
- CAN termination is properly configured
- EOL Hardware firmware/hardware provides correct I2C pull-up and ADC/DAC calibration; Host consumes CAN feedback values

---

## 11. Glossary

| Term | Definition |
|------|------------|
| ADC | Analog-to-Digital Converter (ADS1115) |
| CAN | Controller Area Network communication protocol |
| DAC | Digital-to-Analog Converter (MCP4725) |
| EOL | End-of-Line (final production testing phase) |
| IPC | Industrial Control Panel (test target device) |
| MUX | Analog Multiplexer (signal router) |
| GPIO | General Purpose Input/Output pins |
| I2C | Inter-Integrated Circuit communication bus (used by EOL Hardware; Host communicates with devices via CAN) |
| SocketCAN | Linux CAN bus socket interface |
| GPIO | General Purpose Input/Output pins (implemented on EOL Hardware; Host controls them via CAN) |
| BCM | Broadcom GPIO numbering scheme |

---

## 12. Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Oct 2025 | AI Agent | Initial comprehensive requirements document |

---

**Document Status:** Draft  
**Next Review Date:** TBD  
**Approver:** [Engineering Manager]
