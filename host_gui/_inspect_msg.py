import os, sys
import cantools
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dbc_path = os.path.join(repo_root, 'docs', 'can_specs', 'eol_firmware.dbc')
db = cantools.database.load_file(dbc_path)
msg = next((m for m in getattr(db,'messages',[]) if getattr(m,'frame_id',None)==272), None)
print('Message:', msg.name)
for s in msg.signals:
    print('Signal:', s.name, 'start', s.start, 'length', s.length, 'mux', getattr(s,'multiplexer_ids', None))
    try:
        print('  choices:', getattr(s,'choices', None))
    except Exception:
        pass
    try:
        print('  is_multiplexer?', getattr(s,'multiplexer_signal', False))
    except Exception:
        pass
