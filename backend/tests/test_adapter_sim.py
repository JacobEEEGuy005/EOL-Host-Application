import time
from backend.adapters.sim import SimAdapter
from backend.adapters.interface import Frame


def test_sim_adapter_send_recv():
    a = SimAdapter()
    a.open()
    f = Frame(can_id=0x100, data=b"\x01\x02\x03")
    a.send(f)
    r = a.recv(timeout=1.0)
    assert r is not None
    assert r.can_id == 0x100
    assert r.data == b"\x01\x02\x03"
    a.close()


def test_sim_iter_recv():
    a = SimAdapter()
    a.open()
    frames = [Frame(can_id=i, data=bytes([i & 0xFF])) for i in range(3)]
    for fr in frames:
        a.send(fr)
    # consume via iterator
    seen = []
    for idx, fr in enumerate(a.iter_recv()):
        seen.append(fr)
        if len(seen) >= 3:
            break
    assert len(seen) == 3
    a.close()
