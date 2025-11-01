import os
import sys
try:
    import cantools
except Exception as e:
    print('cantools not available:', e)
    sys.exit(2)

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dbc_path = os.path.join(repo_root, 'docs', 'can_specs', 'eol_firmware.dbc')
print('Loading DBC from', dbc_path)
db = cantools.database.load_file(dbc_path)
msg = None
for m in getattr(db, 'messages', []):
    mid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
    try:
        if mid is not None and int(mid) == 272:
            msg = m
            break
    except Exception:
        continue
if msg is None:
    print('Message 272 not found')
    sys.exit(1)
print('Found message:', msg.name)

# Test 1: mux enable + channel
encode_data = {'DeviceID': 0, 'MessageType': 17, 'MUX_Channel': 3, 'MUX_Enable': 1}
print('Encode data:', encode_data)
try:
    b = msg.encode(encode_data)
    print('Encoded bytes:', b.hex())
except Exception as e:
    print('Encode error:', e)

# Test 2: DAC without MessageType
enc_dac_no_type = {'DeviceID': 0, 'DAC_Voltage_mV': 1000}
print('\nEncode data (no MessageType):', enc_dac_no_type)
try:
    b2 = msg.encode(enc_dac_no_type)
    print('Encoded bytes (no MessageType):', b2.hex())
except Exception as e:
    print('Encode error (no MessageType):', e)

# Test 3: DAC with MessageType=18
enc_dac_with_type = {'DeviceID': 0, 'MessageType': 18, 'DAC_Voltage_mV': 1000}
print('\nEncode data (with MessageType=18):', enc_dac_with_type)
try:
    b3 = msg.encode(enc_dac_with_type)
    print('Encoded bytes (with MessageType):', b3.hex())
except Exception as e:
    print('Encode error (with MessageType):', e)
