import queue
import threading
import time
from typing import Optional, Iterable
from .interface import Adapter, Frame


class SimAdapter:
    """A simple in-memory simulated adapter for testing.

    Usage:
      a = SimAdapter()
      a.open()
      a.send(Frame(...))
      f = a.recv()
      a.close()
    """

    def __init__(self) -> None:
        self._q: queue.Queue[Frame] = queue.Queue()
        self._running = False
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
            self._running = True

    def close(self) -> None:
        with self._lock:
            self._running = False
        # drain queue
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break

    def send(self, frame: Frame) -> None:
        """Enqueue a frame to the receive queue to simulate loopback."""
        # simulate minor latency
        time.sleep(0.001)
        self._q.put(frame)

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        try:
            f = self._q.get(timeout=timeout)
            return f
        except queue.Empty:
            return None

    def iter_recv(self) -> Iterable[Frame]:
        """Yield frames until adapter is closed."""
        while True:
            with self._lock:
                if not self._running and self._q.empty():
                    break
            f = self.recv(timeout=0.5)
            if f is not None:
                yield f
