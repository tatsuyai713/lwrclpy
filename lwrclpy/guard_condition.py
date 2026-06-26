import threading


class GuardCondition:
    """Lightweight guard condition that enqueues a callback when triggered."""

    def __init__(self, callback, enqueue_cb):
        self._callback = callback
        self._enqueue_cb = enqueue_cb
        self._destroyed = False
        self._pending = False
        self._lock = threading.Lock()

    def trigger(self):
        with self._lock:
            if self._destroyed or self._pending:
                return
            self._pending = True
        self._enqueue_cb(self._run_callback, None)

    def _run_callback(self, msg=None):
        try:
            with self._lock:
                if self._destroyed:
                    return
            if msg is None:
                self._callback()
            else:
                self._callback(msg)
        finally:
            with self._lock:
                self._pending = False

    def destroy(self):
        with self._lock:
            self._destroyed = True
            self._pending = False
