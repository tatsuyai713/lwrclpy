import threading


class GuardCondition:
    """Lightweight guard condition that enqueues a callback when triggered."""

    def __init__(self, callback, enqueue_cb):
        self._callback = callback
        self._enqueue_cb = enqueue_cb
        self._destroyed = False
        self._pending = False
        self._lock = threading.Lock()

        # Drop hook: clear the pending flag if a bounded node queue evicts
        # this callback, otherwise trigger() would be a no-op forever.
        def _queued_callback(msg=None, guard=self):
            guard._run_callback(msg)

        _queued_callback._lwrclpy_on_dropped = self._clear_pending
        self._queued_callback = _queued_callback

    def _clear_pending(self):
        with self._lock:
            self._pending = False

    def trigger(self):
        with self._lock:
            if self._destroyed or self._pending:
                return
            self._pending = True
        try:
            self._enqueue_cb(self._queued_callback, None)
        except Exception:
            self._clear_pending()
            raise

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
