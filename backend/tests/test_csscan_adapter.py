import pytest

try:
    import can  # type: ignore
except Exception:
    can = None

from backend.adapters.csscan import CSSCANAdapter
from backend.adapters.interface import Frame


@pytest.mark.skipif(can is None, reason="python-can not installed")
def test_csscan_virtual_loopback():
    # try to use the virtual bus if supported by python-can
    a = CSSCANAdapter(interface="virtual")
    a.open()
    f = Frame(can_id=0x200, data=b"\x05\x06")
    a.send(f)
    r = a.recv(timeout=1.0)
    assert r is not None
    assert r.can_id == 0x200
    assert r.data[:2] == b"\x05\x06"
    a.close()
