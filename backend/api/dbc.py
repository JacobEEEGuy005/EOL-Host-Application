from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
import cantools

router = APIRouter(prefix="/api/dbc", tags=["dbc"])


@router.post("/upload")
async def upload_dbc(request: Request, file: UploadFile = File(...)):
    """Upload a DBC file. Currently a placeholder that accepts the file and
    returns metadata. Full parsing (cantools) will be added in Stage-2.
    """
    fname = (file.filename or "")
    if not fname.lower().endswith(".dbc"):
        raise HTTPException(status_code=400, detail="Only .dbc files supported")
    contents = await file.read()
    try:
        db = cantools.database.load_string(contents.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DBC parse error: {e}")

    # store parsed DBC in app.state.dbcs as a dict filename -> cantools.Database
    if not hasattr(request.app.state, "dbcs"):
        request.app.state.dbcs = {}
    request.app.state.dbcs[fname] = db
    return JSONResponse({"filename": fname, "messages": len(db.messages)})


@router.post("/decode-frame")
async def decode_frame(request: Request, payload: dict):
    """Decode a raw CAN frame using an uploaded DBC.

    Payload: { "can_id": int, "data": "hexstring", "dbc": optional filename }
    """
    can_id = payload.get("can_id")
    data_hex = payload.get("data")
    dbc_name = payload.get("dbc")
    if can_id is None or data_hex is None:
        raise HTTPException(status_code=400, detail="can_id and data are required")
    try:
        data = bytes.fromhex(data_hex)
    except Exception:
        raise HTTPException(status_code=400, detail="data must be a hex string")

    dbs = getattr(request.app.state, "dbcs", {})
    if not dbs:
        raise HTTPException(status_code=404, detail="No DBC uploaded")

    if dbc_name:
        db = dbs.get(dbc_name)
        if db is None:
            raise HTTPException(status_code=404, detail=f"DBC not found: {dbc_name}")
    else:
        # choose the most recently uploaded DBC (insertion order)
        db = list(dbs.values())[-1]

    # Try decoding; if data is shorter than the message length, pad with zeros and retry.
    try:
        decoded = db.decode_message(can_id, data)
    except Exception as e:
        # attempt to pad if the message exists and data is too short
        try:
            msg = db.get_message_by_frame_id(can_id)
        except Exception:
            msg = None
        if msg is None:
            # No message metadata available, return the original error.
            raise HTTPException(status_code=400, detail=f"Decode error: {e}")

        expected_len = getattr(msg, "length", None)
        if expected_len is None:
            raise HTTPException(status_code=400, detail=f"Decode error: {e}")

        if len(data) < expected_len:
            padded = data + b"\x00" * (expected_len - len(data))
            try:
                decoded = db.decode_message(can_id, padded)
            except Exception as e2:
                raise HTTPException(status_code=400, detail=f"Decode error: {e2}")
        else:
            raise HTTPException(status_code=400, detail=f"Decode error: {e}")

    # Ensure signals are JSON-serializable (cantools may return NamedSignalValue objects)
    def _serialize_value(v):
        # If it's already JSON serializable, return as-is
        try:
            import json as _json

            _json.dumps(v)
            return v
        except Exception:
            pass
        # Try common attributes
        if hasattr(v, "value"):
            return getattr(v, "value")
        if hasattr(v, "name"):
            return getattr(v, "name")
        if hasattr(v, "to_dict"):
            return v.to_dict()
        # Fallback to string representation
        return str(v)

    serial = {k: _serialize_value(v) for k, v in decoded.items()} if isinstance(decoded, dict) else _serialize_value(decoded)
    return JSONResponse({"signals": serial})


@router.get("/list")
async def list_dbcs(request: Request):
    dbs = getattr(request.app.state, "dbcs", {})
    return JSONResponse({"dbcs": list(dbs.keys())})
