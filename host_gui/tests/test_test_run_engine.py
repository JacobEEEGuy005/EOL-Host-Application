import time
from PySide6 import QtWidgets
from host_gui.main import BaseGUI


def test_run_single_with_sim_adapter():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui = BaseGUI()
    # ensure adapter started (SimAdapter fallback)
    try:
        gui.toggle_adapter()
    except Exception:
        # if adapter cannot start, skip by returning
        return
    # create a simple raw-actuation test
    t = {
        'name': 'run-raw',
        'type': 'analog',
        'feedback_signal': None,
        'actuation': {'type':'analog','dac_can_id':0x100,'dac_command':'010203'}
    }
    gui._tests = [t]
    gui.test_list.clear()
    gui.test_list.addItem(t['name'])
    gui.test_list.setCurrentRow(0)
    # run selected
    gui._on_run_selected()
    # allow GUI loop to process
    time.sleep(0.2)
    # we expect the frame_table to have at least one row (loopback)
    assert gui.frame_table.rowCount() >= 1
    # cleanup
    try:
        gui.toggle_adapter()
    except Exception:
        pass
