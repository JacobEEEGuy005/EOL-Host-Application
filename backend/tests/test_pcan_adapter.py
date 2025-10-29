import types
import queue

import pytest

import backend.adapters.pcan as pcan_mod
from backend.adapters.interface import Frame


class DummyBus:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sent = []
        self._recv_queue = queue.Queue()

    def send(self, msg):
        # record sent message
        self.sent.append(msg)

    def recv(self, timeout=None):
        try:
            return self._recv_queue.get_nowait()
        except queue.Empty:
            return None

    def shutdown(self):
        pass

    def close(self):
        pass


def test_open_close_and_kwargs(monkeypatch):
    captured = {}

    def fake_bus(**kwargs):
        captured.update(kwargs)
        return DummyBus(**kwargs)

    monkeypatch.setattr(pcan_mod.can, "Bus", fake_bus)

    a = pcan_mod.PcanAdapter(channel="PCAN_TEST", bitrate=250000)
    a.open()
    assert captured.get("channel") == "PCAN_TEST"
    assert captured.get("bustype") == "pcan"
    # bitrate may be passed as int
    assert captured.get("bitrate") == 250000
    a.close()


def test_send_and_loopback(monkeypatch):
    # Provide a Bus with a send implementation
    def fake_bus(**kwargs):
        return DummyBus(**kwargs)

    monkeypatch.setattr(pcan_mod.can, "Bus", fake_bus)

    a = pcan_mod.PcanAdapter()
    a.open()
    f = Frame(can_id=0x123, data=b"\x01\x02\x03", timestamp=1.23)
    a.send(f)

    # recv should first return loopback frame
    got = a.recv(timeout=0.1)
    assert got is not None
    assert got.can_id == f.can_id
    assert got.data == f.data

    a.close()


def test_recv_from_bus(monkeypatch):
    class Msg:
        def __init__(self, arb, data, ts=0.5):
            self.arbitration_id = arb
            self.data = data
            self.timestamp = ts

    class BusWithMsg(DummyBus):
        def recv(self, timeout=None):
            return Msg(0x200, bytearray(b"\x00\x01"), 0.5)

    def fake_bus(**kwargs):
        return BusWithMsg(**kwargs)

    monkeypatch.setattr(pcan_mod.can, "Bus", fake_bus)
    a = pcan_mod.PcanAdapter()
    a.open()
    got = a.recv(timeout=0.1)
    assert got is not None
    assert got.can_id == 0x200
    assert got.data == b"\x00\x01"
    assert abs((got.timestamp or 0) - 0.5) < 1e-6
    a.close()
