import sys
import threading
import json
import queue
import time
import os

from PySide6 import QtCore, QtWidgets

try:
    # Import the SimAdapter from the backend package
    from backend.adapters.sim import SimAdapter
    from backend.adapters.interface import Frame as AdapterFrame
except Exception:
    SimAdapter = None
    AdapterFrame = None


class WorkerThread(threading.Thread):
    def __init__(self, sim, out_q):
        super().__init__(daemon=True)
        self.sim = sim
        self.out_q = out_q
        self._stop = threading.Event()

    def run(self):
        try:
            for frame in self.sim.iter_recv():
                if self._stop.is_set():
                    break
                self.out_q.put(frame)
        except Exception:
            pass

    def stop(self):
        self._stop.set()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('EOL Host - Native GUI')
        self.resize(900, 600)

        self.sim = None
        self.worker = None
        self.frame_q = queue.Queue()

        # UI
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # DBC list
        self.dbc_list = QtWidgets.QListWidget()
        layout.addWidget(QtWidgets.QLabel('Available DBCs:'))
        layout.addWidget(self.dbc_list)

        # Live frames table
        layout.addWidget(QtWidgets.QLabel('Live frames:'))
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['timestamp', 'can_id', 'data'])
        layout.addWidget(self.table)

        # Send frame form
        h = QtWidgets.QHBoxLayout()
        self.id_input = QtWidgets.QLineEdit()
        self.data_input = QtWidgets.QLineEdit()
        send_btn = QtWidgets.QPushButton('Send')
        send_btn.clicked.connect(self.on_send)
        h.addWidget(QtWidgets.QLabel('CAN ID:'))
        h.addWidget(self.id_input)
        h.addWidget(QtWidgets.QLabel('Data (hex):'))
        h.addWidget(self.data_input)
        h.addWidget(send_btn)
        layout.addLayout(h)

        # Start adapter button
        self.start_btn = QtWidgets.QPushButton('Start Sim Adapter')
        self.start_btn.clicked.connect(self.start_adapter)
        layout.addWidget(self.start_btn)

        # Timer to poll the frame queue
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.poll_frames)

        self.load_dbcs()

    def load_dbcs(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        index_path = os.path.join(repo_root, 'backend', 'data', 'dbcs', 'index.json')
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for entry in data.get('dbcs', []):
                    self.dbc_list.addItem(entry.get('original_name') or entry.get('filename'))
            except Exception:
                pass

    def start_adapter(self):
        if SimAdapter is None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'SimAdapter import failed; ensure project is on PYTHONPATH')
            return
        if self.sim is None:
            self.sim = SimAdapter()
            self.sim.open()
            self.worker = WorkerThread(self.sim, self.frame_q)
            self.worker.start()
            self.timer.start()
            self.start_btn.setText('Stop Sim Adapter')
        else:
            try:
                self.worker.stop()
            except Exception:
                pass
            try:
                self.sim.close()
            except Exception:
                pass
            self.sim = None
            self.start_btn.setText('Start Sim Adapter')

    def poll_frames(self):
        try:
            while not self.frame_q.empty():
                f = self.frame_q.get_nowait()
                self.add_frame_row(f)
        except Exception:
            pass

    def add_frame_row(self, frame):
        r = self.table.rowCount()
        self.table.insertRow(r)
        ts = getattr(frame, 'timestamp', '')
        can_id = getattr(frame, 'can_id', '')
        data = getattr(frame, 'data', b'')
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ts)))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(can_id)))
        self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(data.hex() if isinstance(data, (bytes, bytearray)) else str(data)))

    def on_send(self):
        if self.sim is None:
            QtWidgets.QMessageBox.warning(self, 'Not running', 'Start the adapter first')
            return
        try:
            can_id = int(self.id_input.text(), 0)
            data = bytes.fromhex(self.data_input.text())
            if AdapterFrame is not None:
                f = AdapterFrame(can_id=can_id, data=data)
            else:
                # Fallback simple object
                class F:
                    pass
                f = F()
                f.can_id = can_id
                f.data = data
                f.timestamp = time.time()
            # send and loopback
            self.sim.send(f)
            if hasattr(self.sim, 'loopback'):
                try:
                    self.sim.loopback(f)
                except Exception:
                    pass
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to send frame: {e}')


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
