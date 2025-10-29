from fastapi.testclient import TestClient
from backend.api.main import app
from backend import metrics


def setup_function():
    # reset metrics before each test
    metrics.reset_all()


def test_metrics_endpoint_and_sim_send():
    client = TestClient(app)
    # ensure starting metrics empty
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)

    # send a frame via the API which uses the SimAdapter
    payload = {"can_id": 0x100, "data": "010203"}
    r = client.post("/api/send-frame", json=payload)
    assert r.status_code == 200

    # metrics should show at least one sim_send and sim_loopback and sim_recv
    r = client.get("/api/metrics")
    assert r.status_code == 200
    data = r.json()
    # counters exist and are ints
    assert isinstance(data.get("sim_send", 0), int)
    assert data.get("sim_send", 0) >= 1
    assert isinstance(data.get("sim_loopback", 0), int)
    assert data.get("sim_loopback", 0) >= 1
