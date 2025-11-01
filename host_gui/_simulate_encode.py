import os, sys
import cantools
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dbc_path = os.path.join(repo_root, 'docs', 'can_specs', 'eol_firmware.dbc')
print('Loading', dbc_path)
db = cantools.database.load_file(dbc_path)
can_id = 272
signals = {'DAC_Voltage_mV': 1000}
# find target_msg
target_msg = None
for m in getattr(db, 'messages', []):
    mid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
    if mid is not None and int(mid) == int(can_id):
        target_msg = m
        break
print('Target msg:', target_msg.name)
encode_data = {'DeviceID': 0}
# copy signals
for k,v in signals.items():
    encode_data[k] = v
# detect mux_value
mux_value = None
for sig_name in signals:
    for sig in target_msg.signals:
        if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
            mux_value = sig.multiplexer_ids[0]
            break
# set MessageType from mux if present
if mux_value is not None:
    encode_data['MessageType'] = mux_value
else:
    # infer MessageType from MessageType choices matching signal name
    mtype_sig = None
    for s in target_msg.signals:
        if getattr(s,'name','') == 'MessageType':
            mtype_sig = s
            break
    if mtype_sig is not None:
        choices = getattr(mtype_sig, 'choices', None) or {}
        for sig_name in signals:
            sname_up = str(sig_name).upper()
            for val, cname in (choices.items() if hasattr(choices, 'items') else []):
                if sname_up.find('DAC') != -1 and 'DAC' in str(cname).upper():
                    encode_data['MessageType'] = val
                    break
            if 'MessageType' in encode_data:
                break
print('Final encode_data:', encode_data)
try:
    b = target_msg.encode(encode_data)
    print('Encoded bytes:', b.hex())
except Exception as e:
    print('Encode failed:', e)
    sys.exit(1)
