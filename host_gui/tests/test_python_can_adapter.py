import time
from backend.adapters.python_can_adapter import PythonCanAdapter
from backend.adapters.interface import Frame


def test_python_can_virtual_send_recv():
    a = PythonCanAdapter(channel='virtual', interface='virtual')
    try:
        a.open()
    except RuntimeError:
        # python-can not available in environment; skip test
        return
    # send a frame and attempt to receive it
    f = Frame(can_id=0x123, data=b'\x01\x02\x03')
    a.send(f)
    # give receiver a moment
    time.sleep(0.2)
    r = a.recv(timeout=1.0)
    # Close adapter regardless
    a.close()
    assert r is not None
    assert r.can_id == 0x123
    assert r.data.startswith(b'\x01\x02\x03')
