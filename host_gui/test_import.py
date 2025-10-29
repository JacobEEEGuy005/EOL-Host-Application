import sys, os
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
print('sys.path[0]=', sys.path[0])
try:
    import backend.adapters.sim as s
    print('OK', s)
except Exception as e:
    import traceback
    traceback.print_exc()
    print('IMPORT_ERROR:', e)
