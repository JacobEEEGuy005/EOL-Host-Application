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
        # main queue consumed by both recv() and iter_recv()
        self._q: queue.Queue[Frame] = queue.Queue()
        # explicit loopback queue used to guarantee availability to direct
        # recv() callers even if a background reader thread consumes from
        # the main queue first.
        self._loopback_q: queue.Queue[Frame] = queue.Queue()
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

    def loopback(self, frame: Frame) -> None:
        """Explicitly enqueue a frame for loopback/receivers. Use when tests
        or external callers want to guarantee the frame is available to
        `recv()` even if other consumers are present.
        """
        # Put into both the main queue (for iter_recv/background readers)
        # and a dedicated loopback queue reserved for direct recv callers.
        try:
            self._q.put_nowait(frame)
        except Exception:
            self._q.put(frame)
        try:
            self._loopback_q.put_nowait(frame)
        except Exception:
            self._loopback_q.put(frame)

    def recv(self, timeout: Optional[float] = None) -> Optional[Frame]:
        # Prefer frames explicitly looped-back for direct recv callers so
        # tests and synchronous consumers can reliably read a frame even if
        # a background thread is also consuming from the main queue.
        try:
            f = self._loopback_q.get_nowait()
            return f
        except queue.Empty:
            pass
        try:
            f = self._q.get(timeout=timeout)
            return f
        except queue.Empty:
            return None

    def iter_recv(self) -> Iterable[Frame]:
        """Yield frames until adapter is closed."""
        # Use the main queue directly for the background reader so that
        # explicit loopback frames reserved for direct recv() callers are
        # not stolen by the background thread.
        while True:
            with self._lock:
                if not self._running and self._q.empty():
                    break
            try:
                f = self._q.get(timeout=0.5)
            except queue.Empty:
                f = None
            if f is not None:
                yield f
