from fastapi.testclient import TestClient
from backend.api.main import app


def test_send_frame_endpoint_loopback():
    payload = {"can_id": 0x300, "data": "0102"}
    # Use context manager so FastAPI startup events run and app.state.sim is created
    with TestClient(app) as client:
        r = client.post("/api/send-frame", json=payload)
        assert r.status_code == 200
        # simulate consumer reading the loopback frame from the SimAdapter
        sim = app.state.sim
        assert sim is not None
        f = sim.recv(timeout=1.0)
        assert f is not None
        assert f.can_id == 0x300
        assert f.data == bytes.fromhex("0102")
