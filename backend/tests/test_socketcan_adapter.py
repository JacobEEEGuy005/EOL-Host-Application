import types
from backend.adapters.socketcan import SocketCanAdapter
from backend import metrics


class FakeBus:
    def __init__(self):
        self.sent = []
        self._recv_queue = []

    def send(self, msg):
        # record send
        self.sent.append(msg)

    def recv(self, timeout=None):
        if self._recv_queue:
            return self._recv_queue.pop(0)
        return None

    def shutdown(self):
        pass


class FakeMsg:
    def __init__(self, arbitration_id, data, timestamp=None):
        self.arbitration_id = arbitration_id
        self.data = data
        self.timestamp = timestamp


def test_socketcan_send_and_recv(monkeypatch):
    # patch can.Bus to return our FakeBus
    import backend.adapters.socketcan as sc_mod

    def fake_bus_ctor(**kwargs):
        return FakeBus()

    monkeypatch.setattr(sc_mod.can, "Bus", lambda **kw: fake_bus_ctor(**kw))

    metrics.reset_all()
    a = SocketCanAdapter(channel="vcan0")
    a.open()
    # send frame
    from backend.adapters.interface import Frame

    f = Frame(can_id=0x200, data=b"\x01\x02")
    a.send(f)
    # loopback should make recv() return immediately
    got = a.recv(timeout=0.1)
    assert got is not None
    assert got.can_id == 0x200
    # metrics incremented
    m = metrics.get_all()
    assert m.get("socketcan_send", 0) >= 1
    assert m.get("socketcan_recv", 0) >= 1
