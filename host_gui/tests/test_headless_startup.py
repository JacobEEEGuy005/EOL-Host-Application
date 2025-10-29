import os
import sys
import time

# ensure repo root on sys.path (same logic as main)
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import host_gui.main as mg


def test_headless_startup_and_adapter_toggle(monkeypatch):
    """Headless smoke test: instantiate BaseGUI and toggle a fake SimAdapter on/off."""
    # create a fake SimAdapter class to avoid hardware dependencies
    class FakeSim:
        def __init__(self):
            self.opened = False
        def open(self):
            self.opened = True
        def close(self):
            self.opened = False
        def iter_recv(self):
            # generator that yields nothing
            if False:
                yield None
        def send(self, frame):
            pass
        def loopback(self, frame):
            # emulate immediate loopback
            try:
                # put a simple object into the GUI's queue if available
                pass
            except Exception:
                pass

    # patch the module's SimAdapter to our FakeSim
    monkeypatch.setattr(mg, 'SimAdapter', FakeSim)

    # ensure any existing QApplication is cleared; create one for widget construction
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    gui = mg.BaseGUI()

    # start adapter
    gui.device_combo.clear()
    gui.device_combo.addItem('SimAdapter')
    gui.device_combo.setCurrentText('SimAdapter')
    gui.toggle_adapter()
    assert gui.sim is not None
    assert isinstance(gui.sim, FakeSim)

    # stop adapter
    gui.toggle_adapter()
    assert gui.sim is None

    # cleanup
    try:
        app.quit()
    except Exception:
        pass
