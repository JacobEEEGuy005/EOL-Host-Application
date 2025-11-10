from PySide6 import QtWidgets
from host_gui.main import BaseGUI


def test_edit_switch_to_digital_updates_preview():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui = BaseGUI()
    # create analog test
    t = {
        'name': 'analog-for-edit',
        'type': 'Analog Sweep Test',
        'feedback_signal': None,
        'actuation': {'type':'Analog Sweep Test', 'dac_can_id':0x200, 'dac_command_signal':'CMD'}
    }
    gui._tests = [t]
    gui.test_list.clear()
    gui.test_list.addItem(t['name'])
    gui.test_list.setCurrentRow(0)
    # open edit dialog programmatically: emulate double click call
    gui._on_edit_test(gui.test_list.currentItem())
    # in the edit dialog user would switch type; simulate by updating the test entry directly
    t2 = gui._tests[0]
    t2['type'] = 'Digital Logic Test'
    t2['actuation'] = {'type':'Digital Logic Test','can_id':0x100,'signal':'SW','value_low':'1','value_high':'1'}
    gui._tests[0] = t2
    # refresh preview
    gui._on_select_test(None, None)
    # JSON preview should reflect the updated type
    txt = gui.json_preview.toPlainText()
    assert '"type": "Digital Logic Test"' in txt
