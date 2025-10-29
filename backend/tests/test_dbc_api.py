import json
from fastapi.testclient import TestClient

from backend.api.main import app


def test_upload_and_decode_roundtrip():
    client = TestClient(app)
    # Minimal DBC content with one message (id 123) and one 8-bit signal at bit 0.
    dbc = """
VERSION "1.0"
NS_ :
BS_:
BU_: ECU
BO_ 123 MyMessage: 8 ECU
 SG_ Signal1 : 0|8@1+ (1,0) [0|255] "" ECU
"""

    files = {"file": ("test.dbc", dbc, "text/plain")}
    r = client.post("/api/dbc/upload", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("filename") == "test.dbc"
    assert body.get("messages") == 1

    # Now decode a frame with CAN ID 123 and payload 0x05
    payload = {"can_id": 123, "data": "05", "dbc": "test.dbc"}
    r2 = client.post("/api/dbc/decode-frame", json=payload)
    assert r2.status_code == 200, r2.text
    decoded = r2.json()
    # Expect the signal value to be 5
    signals = decoded.get("signals")
    assert signals is not None
    assert signals.get("Signal1") == 5
