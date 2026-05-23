import queue
import threading


class CallbackQueue:
    def __init__(self):
        self._queue = queue.SimpleQueue()
        self._closed = False
        self._stop = object()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, callback, msg):
        if not self._closed:
            self._queue.put((callback, msg))

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._queue.put(self._stop)
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.2)

    def _run(self):
        for item in iter(self._queue.get, self._stop):
            callback, msg = item
            try:
                callback(msg)
            except Exception:
                pass