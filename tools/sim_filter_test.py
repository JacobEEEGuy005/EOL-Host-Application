import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.adapters.sim import SimAdapter
from backend.adapters.interface import Frame
import time

print('Creating SimAdapter')
a = SimAdapter()
a.open()
print('Set filter to only allow CAN ID 0x123')
a.set_filters([{'can_id': 0x123, 'extended': False}])
# loopback a non-matching frame
f1 = Frame(can_id=0x200, data=b'\x01\x02')
print('Loopback non-matching frame id=0x200')
a.loopback(f1)
# loopback a matching frame
f2 = Frame(can_id=0x123, data=b'\xAA')
print('Loopback matching frame id=0x123')
a.loopback(f2)

# try recv twice with timeout
r1 = a.recv(timeout=0.5)
print('Recv1:', None if r1 is None else hex(r1.can_id), getattr(r1,'data',None))
r2 = a.recv(timeout=0.5)
print('Recv2:', None if r2 is None else hex(r2.can_id), getattr(r2,'data',None))

# test iter_recv: put one non-matching, one matching, then iterate a few
import threading

def producer():
    time.sleep(0.1)
    a.loopback(Frame(can_id=0x200, data=b'\x00'))
    a.loopback(Frame(can_id=0x123, data=b'\x01'))

t = threading.Thread(target=producer, daemon=True)

print('Starting iter_recv test')
t.start()
count = 0
for f in a.iter_recv():
    print('iter_recv got', hex(f.can_id), f.data)
    count += 1
    if count >= 1:
        break

print('Done')
