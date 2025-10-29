import os
import json
from PySide6 import QtWidgets
from host_gui.main import BaseGUI, repo_root


def test_save_and_load_tests(tmp_path):
    # create a temporary QApplication for widget creation
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui = BaseGUI()
    # prepare sample tests
    sample = {
        'name': 'sample-dig',
        'type': 'digital',
        'feedback_signal': 'IGN_SW',
        'actuation': {'type': 'digital', 'can_id': 0x100, 'signal': 'SW_CMD', 'value': '1'}
    }
    gui._tests = [sample]
    # save
    gui._on_save_tests()
    p = os.path.join(repo_root, 'backend', 'data', 'tests', 'tests.json')
    assert os.path.exists(p)
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert isinstance(data.get('tests'), list)
    # clear and load
    gui._tests = []
    gui._on_load_tests()
    assert len(gui._tests) >= 1
    # cleanup
    try:
        os.remove(p)
    except Exception:
        pass
