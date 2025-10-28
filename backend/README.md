# Backend service (Stage 1)

This folder contains the FastAPI backend for the EOL Host Application. For Stage 1 we provide a minimal app and a health endpoint used by smoke tests and the frontend.

Run locally (development):

```bash
python -m venv .venv
# On Windows use: .\.venv\Scripts\Activate.ps1 or .\.venv\Scripts\activate.bat
source .venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn
uvicorn backend.api.main:app --reload --port 8000
```

API endpoints:
- GET /api/health — returns simple service health JSON
- GET / — serves `frontend/dist/index.html` when present, otherwise a simple HTML page
# Backend

This folder will contain the FastAPI backend for the EOL Host Application.

Contents (planned):
- `backend/api/` - FastAPI app modules
- `backend/adapters/` - CAN adapter implementations
- `backend/tests/` - unit tests

Run (development):
```bash
# from repository root
python -m venv .venv
.venv\Scripts\activate   # Windows
# or
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
# run the app during development (uvicorn)
# uvicorn backend.api.main:app --reload --port 8000
```
