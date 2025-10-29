import cantools
import os

# Load DBC
dbc_path = os.path.join(os.path.dirname(__file__), 'backend', 'data', 'dbcs', 'eol_firmware.dbc')
db = cantools.database.load_file(dbc_path)

# Find message
msg = None
for m in db.messages:
    if m.frame_id == 272:
        msg = m
        break

if msg:
    print(f"Message: {msg.name}, ID: {msg.frame_id}, DLC: {msg.length}")
    print("Signals:")
    for sig in msg.signals:
        print(f"  {sig.name}: start={sig.start}, length={sig.length}, is_multiplexer={sig.is_multiplexer}, multiplexer_ids={sig.multiplexer_ids}")

    # Encode
    enc = {'DeviceID': 0, 'MessageType': 16, 'CMD_Relay_1': 1, 'CMD_Relay_2': 0, 'CMD_Relay_3': 0, 'CMD_Relay_4': 0}
    data = msg.encode(enc)
    print(f"Encoded data: {data.hex()}")
    print(f"Length: {len(data)}")

    # Decode back
    decoded = msg.decode(data)
    print(f"Decoded: {decoded}")
else:
    print("Message not found")