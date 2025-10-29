# Stage-2 Preview Release Announcement

This repository has a new Stage‑2 preview release available as a draft on GitHub.

Highlights in this preview:

- DBC upload and decode endpoints:
  - `POST /api/dbc/upload` — upload a DBC file (parsed via cantools)
  - `POST /api/dbc/decode-frame` — decode a raw CAN frame using an uploaded DBC
  - `GET  /api/dbc/list` — list uploaded DBC filenames

- End-to-end test coverage:
  - An e2e pytest was added: `backend/tests/test_dbc_e2e.py` that uploads `docs/can_specs/eol_firmware.dbc`, decodes a multiplexed `Status_Data` message, and verifies broadcast over `/ws/frames`.

- CI updates:
  - The backend test workflow runs the new e2e test on GitHub Actions (Linux and Windows runners).

How to try locally

1. Create/activate Python 3.11 venv and install requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

2. Run tests:

```powershell
python -m pytest -q
```

3. Run the backend and open the WebSocket test page (dev only):

```powershell
python -m uvicorn backend.api.main:app --reload
# then visit http://127.0.0.1:8000/ws_test.html (if present)
```

Notes and next steps

- This is a preview release to collect feedback. In Stage‑2 we will:
  - Harden DBC handling and storage, add persistence for uploaded DBCs.
  - Implement `backend/adapters/csscan.py` hardware adapter wiring and docs for RPI.
  - Add more e2e scenarios and CI gating for hardware tests where applicable.

For questions or to review the release draft, see the GitHub Releases page for this repository.
