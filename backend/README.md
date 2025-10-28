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
