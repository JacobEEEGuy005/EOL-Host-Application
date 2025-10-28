# End-of-Line (EOL) Host Application - Project Requirements

**Project Name:** EOL Testing Application for Integrated Power Converter (IPC)  
**Version:** 1.1  
**Date:** October 2025  
**Organization:** Ergon Mobility Pvt Ltd  
**Platform:** Linux, Windows


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

**REQ-HW-002a:** For Raspberry Pi 5 targets prefer a 64-bit OS (Ubuntu 22.04 / Raspberry Pi OS 64-bit). Ensure the test user is added to the `dialout` (serial) and appropriate groups and that `can-utils` is available for diagnostics.

**REQ-HW-002b:** For Linux builds targeting Raspberry Pi 5 (arm64), perform native builds and verification on Raspberry Pi OS (64-bit) to ensure binary compatibility and proper validation of vendor drivers and system libraries. Cross-builds may be used for CI, but at least one native build/validation pass on Raspberry Pi OS is required prior to release.

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
- AI Agent to update software dependencies based on new requirements

### 5.1 Overview
The project uses a Web UI (frontend) and a Python backend (service) that owns CAN hardware. The backend exposes REST and WebSocket endpoints consumed by the frontend.

### 5.2 Frontend (Presentation Layer)
- Recommended stack: React + TypeScript (or Vue/Svelte) built with Vite
- Node.js LTS (18.x or 20.x)
- Frontend libraries: Chart.js / Recharts / Plotly.js for real-time plotting; optional UI library (Material UI, Ant Design)

### 5.3 Backend (Runtime & Libraries)
- **Python:** 3.11+
- **FastAPI** — REST + WebSocket API
- **Uvicorn[standard]** — ASGI server
- **python-can** == 4.5.* — CAN bus abstraction
- **python-can-csscan-serial==2.4.1** — CL2000 / csscan serial backend (install from PyPI)
- **canalystii** == 0.1 — CANalyst-II adapter (where used)
- **cantools** — DBC parsing and signal decode/encode
- **pyserial** — serial port access for CL2000 and other serial devices
- **pydantic** — configuration validation for `parameters.json`
- **pytest** — unit testing

Optional server-side libraries (for report export or heavy numeric processing):
- **numpy**
- **matplotlib** (for server-side plots or PDF exports)

### 5.4 System Tools & Debugging
- **can-utils** (Linux) — SocketCAN utilities for testing (candump, cansend, slcand)

### 5.5 Packaging & Build Tools
- **PyInstaller** (optional) — create Windows single-binary of backend
- **Docker** (optional) — build and distribute backend images (arm64 for RPi 5)
- **GitHub Actions** — CI matrix builds (windows-latest, ubuntu-latest, ubuntu-arm64) recommended

Notes:
- The previous PyQt5 desktop requirement has been replaced by the Web UI + backend architecture. If a desktop single-executable is required, the web UI can be packaged with Electron or the backend and frontend can be bundled together.
- Linux/arm64 builds intended for Raspberry Pi 5 must be built and validated on Raspberry Pi OS (64-bit). CI may perform cross-builds, but release artifacts for RPi must be produced from a native Raspberry Pi OS environment (or validated there) to ensure correct libc/ABI, kernel module and driver compatibility.

---

## 6. System Architecture
- AI Agent to update System Architecture to suit new requirements.

### 6.1 Application Layers (updated for Web UI)

```
┌─────────────────────────────────────┐
│ Presentation Layer (Web UI, React)  │
│ - frontend/ (Vite + React + TS)     │
│ - served as static files by backend │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│ Backend / Business Logic (FastAPI)  │
│ - API: REST (control/config)        │
│ - Realtime: WebSocket (frame stream)│
│ - test_runner.py, parameters.json   │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│ Hardware Abstraction Layer (Adapters)│
│ - python-can adapter plugins (pcan,  │
│   vector, csscan, socketcan, sim)    │
│ - EOL Hardware (STM32) over CAN      │
└──────────────────────────────────────┘
```

### 6.2 Threading & Concurrency Model

**REQ-ARCH-001:** Presentation is a browser client; the backend must be designed to keep the API event loop non-blocking.

**REQ-ARCH-002:** Test runners shall execute in backend background workers or async tasks so REST/WebSocket responsiveness is preserved.

**REQ-ARCH-003:** A CAN listener shall run as a background task or dedicated thread in the backend, feeding a thread-safe queue consumed by test runners and WebSocket broadcasters.

**REQ-ARCH-004:** Frontend updates are triggered via WebSocket messages; the frontend must implement reconnection and idempotent handling of events.

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

**REQ-DEP-001:** Installation shall be achievable via separate backend and frontend steps:

Backend (Python):
```bash
git clone <repository>
cd EndOfLine-Testing
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Frontend (development or build):
```bash
cd frontend
npm install
npm run build   # produces static files in frontend/dist
```

**REQ-DEP-002:** Virtual environment usage shall be documented but optional

### 8.2 Configuration

**REQ-DEP-003:** Logo image (`ergon.jpg`) must be present in project root

**REQ-DEP-004:** `parameters.json` must be present and valid

### 8.3 Execution

**REQ-DEP-007:** Backend service shall start via ASGI server (example):
```bash
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

The backend will serve the built frontend static files in production or the UI may be packaged using Electron if a desktop single-executable is desired.

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

## 13. Build Plan & Milestones

This section defines a staged implementation plan with clear milestones, acceptance criteria and expected artifacts for each stage. The plan is written to support iterative delivery, quick validation on Raspberry Pi 5 (arm64) and Windows, and continuous integration.

Stage 0 — Project Setup & Developer Environment (milestone M0)
- Goal: Create repository layout, developer guides, basic CI skeleton, and local dev environment for backend and frontend.
- Acceptance criteria:
   - `backend/` and `frontend/` folders exist with minimal README
   - `requirements.txt` and `package.json` created with pinned versions
   - GitHub Actions basic workflow that runs lint and tests on push (windows + ubuntu)
   - Developer onboarding doc: build + run instructions for Windows and RPi (WSL/WSL2 guidance)
   - Required tools and libraries are installed locally and verified: Python 3.11+, pip, Node.js (LTS), npm, `pip` packages from `requirements.txt`, and frontend dependencies via `npm install`.
   - Verification scripts (`scripts/verify_environment.sh` for Linux/macOS and `scripts/verify_environment.cmd` for Windows) are added and produce machine-readable verification artifacts under `build/verify_environment/verification-<os>-<timestamp>.txt`.
   - Verification succeeds on at least one representative host per platform (Windows and Raspberry Pi 5 / Ubuntu-arm64) and verification artifacts are committed or uploaded to CI artifacts so the AI agent can read them.
   - CI includes a verification job that runs the verification scripts on `ubuntu-latest` and `windows-latest` runners and stores the resulting verification artifacts.
   - Git repository initialized with a default branch `main` and initial commit.
   - `.gitignore` present and configured to ignore typical Python, Node, and OS artifacts (venv, node_modules, build outputs, editors); sample `.gitignore` added to root.
   - Branch-based workflow (GitHub Flow) is configured and documented:
      - Use short-lived feature branches (e.g., `feature/`, `fix/`, `chore/`) branched off `main`.
      - All changes are introduced via pull requests (PRs) targeting `main`.
      - PRs require at least one approving review and passing CI (lint + tests) before merge.
      - Protect `main` with branch protection rules (require PR reviews and green CI) and enable required status checks.
   - Commit and PR hygiene:
      - Make regular, small, focused commits with professional messages describing intent and scope.
      - Adopt a commit message convention (recommendation: Conventional Commits) and include meaningful changelog entries.
      - Use `CHANGELOG.md` with at least `Unreleased` section; update on merge/ release.
   - Repository metadata and governance artifacts present: `README.md` (basic build/run), `CONTRIBUTING.md` (branching + PR process), and `.github/PULL_REQUEST_TEMPLATE.md`.
- Artifacts: repo skeleton, READMEs, CI pipeline stub
- Estimated time: 1 week

Stage 1 — Backend Core & CAN Adapters (milestone M1)
- Goal: Implement FastAPI backend, CAN adapter interface, and three adapters: SocketCAN (sim/vcan), CL2000 (`python-can-csscan-serial`), and PCAN (pcan/pcanbasic or socketcan where available).
- Acceptance criteria:
   - Backend serves health endpoint `/api/health` and static frontend files
   - CAN adapter interface documented and implemented for `socketcan`, `csscan` and `pcan` (or adapter shim to PCANBasic)
   - Unit tests covering adapter open/close/send/recv using mocks and vcan
   - Local WebSocket `/ws/frames` streams CAN frames (sim adapter emits test frames)
- Artifacts: `backend/` service, example config, unit tests, adapter docs
- Estimated time: 2–3 weeks

Stage 2 — Frontend Skeleton & Realtime Integration (milestone M2)
- Goal: Implement minimal React app that connects to REST and WebSocket endpoints, shows connection status, and renders a live frame table and simple plot.
- Acceptance criteria:
   - Frontend connects to backend, displays CAN status, and updates live frame list via WebSocket
   - Basic plot of simulated analog sweep data using Chart.js or Recharts
   - Frontend build artifacts served by backend in production mode
- Artifacts: `frontend/` build, integration tests (E2E smoke with simulated adapter)
- Estimated time: 2 weeks

Stage 3 — Test Runner, Configuration & DBC Integration (milestone M3)
- Goal: Implement test runner, `parameters.json` schema, JSON configurator endpoints, and DBC decoding (cantools) support.
- Acceptance criteria:
   - `parameters.json` schema v1 validated by backend (Pydantic)
   - DBC files can be uploaded/selected via API and are used to decode incoming CAN frames
   - Implemented digital relay and analog sweep test flows per requirements (timeout constants configurable)
   - Test results persisted to local SQLite or JSON files with export to CSV/TXT
- Artifacts: test_runner implementation, parameters.json examples, DBC handling, report exports
- Estimated time: 3–4 weeks

Stage 4 — Hardware Validation & Driver Interop (milestone M4)
- Goal: Validate real hardware on Windows and RPi 5: PCAN, CANalyst-II, and CL2000. Implement any platform-specific shims and documentation for driver installation.
- Acceptance criteria:
   - PCAN device tested on Windows and, where applicable, on Linux with PEAK drivers
   - CANalyst-II tested on Windows via `canalystii` adapter
   - CL2000 tested via `python-can-csscan-serial` on Windows and on RPi (serial permissions, baud settings validated)
   - Documented driver install steps and troubleshooting notes
- Artifacts: hardware test logs, updated README with vendor driver install steps, any adapter patches
- Estimated time: 2 weeks (may vary by hardware access)

Stage 5 — Packaging, Deployment & CI (milestone M5)
- Goal: Create build artifacts for Windows (PyInstaller) and Linux (Deb/arm64 binary or Docker image). Implement CI that builds and artifacts packages for both platforms.
- Acceptance criteria:
   - GitHub Actions builds Windows executable and Linux (x64 and arm64) artifacts
   - systemd service template for RPi and Windows service/installer notes included
   - Smoke tests run against packaged artifact in CI (using simulated adapters)
 -   RPi (arm64) artifacts are built and validated on Raspberry Pi OS (64-bit) or produced by a native Raspberry Pi OS build machine; CI must include a validation step that runs the packaged artifact on Raspberry Pi OS (physical device or validated image) and stores logs/artifacts.
- Artifacts: installers/artifacts, CI workflows, systemd file, packaging docs
- Estimated time: 2–3 weeks

Stage 6 — Validation, Field Testing & Performance Tuning (milestone M6)
- Goal: Run extended validation on production hardware, optimize timing, and ensure reliability goals (1000+ runs, reconnection behavior).
- Acceptance criteria:
   - 100 consecutive test runs pass on a target bench (or documented failures with mitigation)
   - CAN reconnection tests pass within defined retry windows
   - Performance profiling completed; CPU/memory usage within acceptable limits on RPi 5
- Artifacts: field test reports, performance tuning notes
- Estimated time: 2–4 weeks

Stage 7 — Documentation, Training & Handover (milestone M7)
- Goal: Finalize user and developer documentation, training slides, and handover materials to operations/QA.
- Acceptance criteria:
   - User guide and operator checklist created
   - Developer README with architecture, build, and extension guide
   - Training session completed and acceptance sign-off
- Artifacts: docs, slides, recorded demo
- Estimated time: 1–2 weeks

Risks & Mitigations
- Vendor drivers (Vector/PCAN) availability on Linux — mitigation: provide Windows gateway/proxy approach and document fallbacks.
- Timing/latency constraints — mitigation: keep timing-critical I/O in backend; prefer kernel timestamps (SocketCAN/PCANBasic) and measure in Stage 6.
- Hardware access / flakiness — mitigation: provide robust simulation adapters and CI tests using vcan.

KPIs & Success Criteria
- All core features (digital tests, analog sweeps, report exports) pass automated unit and integration tests.
- System can run 100 consecutive test cycles without memory growth; CAN reconnection behavior meets requirements.
- Frontend behaves responsively on Raspberry Pi 5 and Windows; live plots update at target rates (>=10 FPS) under test load.

Next steps
- Choose which milestone to start first (recommended: Stage 0 → Stage 1). I can scaffold Stage 0 or Stage 1 immediately (create `backend/` and `frontend/` skeletons, `requirements.txt`, `package.json`, and CI stub).

## 12. Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Oct 2025 | AI Agent | Initial comprehensive requirements document |
| 1.1 | Oct 2025 | AI Agent | Updated to Web UI + Python backend architecture; added FastAPI, python-can-csscan-serial, frontend stack and RPi deployment notes |
| 1.2 | Oct 2025 | AI Agent | Added staged build plan and milestones for implementation and verification |

---

**Document Status:** Draft  
**Next Review Date:** TBD  
**Approver:** [Engineering Manager]

---
