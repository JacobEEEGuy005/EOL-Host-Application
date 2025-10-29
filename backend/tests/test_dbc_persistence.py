import os
from fastapi.testclient import TestClient

from backend.api.main import app


def _dbcs_dir():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "backend", "data", "dbcs")


def test_dbc_persistence_list_after_restart():
    # minimal DBC content
    dbc = """
VERSION "1.0"
NS_ :
BS_:
BU_: ECU
BO_ 200 PersistMsg: 8 ECU
 SG_ SigA : 0|8@1+ (1,0) [0|255] "" ECU
"""

    fname = "persist_test.dbc"
    files = {"file": (fname, dbc, "text/plain")}

    # ensure clean state for this test file
    dbs_dir = _dbcs_dir()
    os.makedirs(dbs_dir, exist_ok=True)
    target = os.path.join(dbs_dir, fname)
    if os.path.exists(target):
        os.remove(target)

    # Upload using a client (starts app lifespan)
    with TestClient(app) as client:
        r = client.post("/api/dbc/upload", files=files)
        assert r.status_code == 200, r.text

    # Simulate restart by creating a new TestClient which triggers lifespan and should load persisted DBCs
    with TestClient(app) as client2:
        r2 = client2.get("/api/dbc/list")
        assert r2.status_code == 200
        body = r2.json()
        assert "dbcs" in body
        # list returns metadata entries; ensure an entry with our filename exists
        files = body["dbcs"]
        assert any(f.get("filename") == fname for f in files), files
