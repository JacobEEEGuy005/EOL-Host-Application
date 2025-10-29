import json
import os
from fastapi.testclient import TestClient


def test_dbc_upload_decode_and_ws_loopback():
    """End-to-end test:
    - Upload a real DBC from docs/can_specs
    - Decode a zeroed frame via /api/dbc/decode-frame and assert expected signals exist
    - Open a WebSocket to /ws/frames, POST /api/send-frame and verify the raw frame is broadcast
    """
    from backend.api.main import app

    # Use context manager so the FastAPI lifespan (startup) runs and app.state is initialized
    with TestClient(app) as client:
        # upload the repo DBC file
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        dbc_path = os.path.join(repo_root, "docs", "can_specs", "eol_firmware.dbc")
        assert os.path.exists(dbc_path), f"DBC not found at {dbc_path}"

        with open(dbc_path, "rb") as fh:
            dbc_contents = fh.read()

        files = {"file": ("eol_firmware.dbc", dbc_contents, "text/plain")}
        r = client.post("/api/dbc/upload", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("filename") == "eol_firmware.dbc"

        # decode a frame for CAN ID 256 (Status_Data, 8 bytes).
        # The DBC message is multiplexed; set the multiplexer (MessageType) to 5 ("Status")
        # and DeviceID to 1 so the multiplexer selection is valid.
        payload = {"can_id": 256, "data": "01" + "05" + ("00" * 6), "dbc": "eol_firmware.dbc"}
        r2 = client.post("/api/dbc/decode-frame", json=payload)
        assert r2.status_code == 200, r2.text
        signals = r2.json().get("signals", {})
        # Basic sanity: the DBC defines DeviceID and MessageType for BO_ 256
        assert "DeviceID" in signals or "MessageType" in signals

        # Now verify websocket broadcast receives the same raw frame
        with client.websocket_connect("/ws/frames") as ws:
            r3 = client.post("/api/send-frame", json={"can_id": 256, "data": "01" + "05" + ("00" * 6)})
            assert r3.status_code == 200, r3.text
            text = ws.receive_text()
            msg = json.loads(text)
            assert msg.get("can_id") == 256
            assert msg.get("data") == ("01" + "05" + ("00" * 6))
