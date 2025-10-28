from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import os

app = FastAPI(title="EOL Host Backend")


@app.get("/api/health")
def health():
    """Simple health endpoint for Stage 1 smoke tests."""
    return {"status": "ok", "service": "eol-host-backend", "version": "0.1-stage1"}


@app.get("/")
def index():
    """Serve frontend index.html if present (production build), otherwise return a simple HTML page."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    index_path = os.path.join(repo_root, "frontend", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<html><body><h1>EOL Host Backend</h1><p>Frontend not built.</p></body></html>")
