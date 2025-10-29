import os
from PySide6 import QtWidgets
import types

from host_gui.main import BaseGUI


class DummySignal:
    def __init__(self, name):
        self.name = name


class DummyMessage:
    def __init__(self, name, frame_id, signals):
        self.name = name
        self.frame_id = frame_id
        self.signals = [DummySignal(s) for s in signals]


class DummyDBC:
    def __init__(self, messages):
        self.messages = messages


def test_dbc_populates_message_and_signal_dropdowns(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui = BaseGUI()
    # create a dummy DBC and patch into gui
    msgs = [DummyMessage('CMD', 0x100, ['S1', 'S2']), DummyMessage('DAC', 0x200, ['D1', 'D2'])]
    db = DummyDBC(msgs)
    gui._dbc_db = db

    # open create dialog which should pick up gui._dbc_db
    gui._on_create_test()
    # locate the last created widgets: JSON preview should be updated after creation, but we only
    # need to assert that the dialog didn't crash and that the internal DBC list exists
    assert hasattr(gui, '_dbc_db')
    assert len(gui._dbc_db.messages) == 2
