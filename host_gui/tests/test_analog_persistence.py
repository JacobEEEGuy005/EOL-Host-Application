import os
import json
from PySide6 import QtWidgets
from host_gui.main import BaseGUI, repo_root


def test_analog_save_load_roundtrip(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui = BaseGUI()
    entry = {
        'name': 'analog-sample',
        'type': 'Analog Sweep Test',
        'feedback_signal': 'FB_SIG',
        'actuation': {
            'type': 'Analog Sweep Test',
            'dac_can_id': 0x123,
            'dac_command_signal': 'DAC_CMD',
            'mux_enable_signal': 'MUX_EN',
            'mux_channel_signal': 'MUX_CH',
            'mux_channel_value': 5,
            'dac_min_mv': 0,
            'dac_max_mv': 3300,
            'dac_step_mv': 100,
            'dac_dwell_ms': 50,
        }
    }

    gui._tests = [entry]
    gui._on_save_tests()
    p = os.path.join(repo_root, 'backend', 'data', 'tests', 'tests.json')
    assert os.path.exists(p)
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
    loaded = data.get('tests', [])
    assert len(loaded) == 1
    a = loaded[0].get('actuation', {})
    # ensure numeric fields preserved as numbers (or strings that represent numbers)
    assert int(a.get('dac_can_id', 0)) == 0x123
    assert a.get('dac_command_signal') == 'DAC_CMD'
    assert a.get('mux_enable_signal') == 'MUX_EN'
    assert int(a.get('mux_channel_value', 0)) == 5
    assert int(a.get('dac_min_mv', 0)) == 0
    assert int(a.get('dac_max_mv', 0)) == 3300
    # cleanup
    try:
        os.remove(p)
    except Exception:
        pass
