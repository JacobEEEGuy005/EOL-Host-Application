from fastapi.testclient import TestClient
from backend.api.main import app


client = TestClient(app)


def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "service" in data
