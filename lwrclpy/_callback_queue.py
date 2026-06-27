import asyncio
import os
import queue
import threading


class CallbackQueue:
    def __init__(self, maxsize: int | None = None, *, drop_policy: str | None = None):
        if maxsize is None:
            try:
                maxsize = int(os.environ.get("LWRCLPY_CALLBACK_QUEUE_MAXSIZE", "0"))
            except Exception:
                maxsize = 0
        self._drop_policy = drop_policy or os.environ.get("LWRCLPY_CALLBACK_QUEUE_DROP_POLICY", "drop_oldest")
        self._drop_count = 0
        self._bounded = int(maxsize) > 0
        self._queue = queue.Queue(maxsize=max(1, int(maxsize))) if self._bounded else queue.SimpleQueue()
        self._closed = False
        self._lock = threading.Lock()
        self._stop = object()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, callback, msg):
        item = (callback, msg)
        with self._lock:
            if self._closed:
                return
            if not self._bounded:
                self._queue.put(item)
                return
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self._drop_count += 1
                if self._drop_policy == "drop_newest":
                    return
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    pass

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if not self._bounded:
                self._queue.put(self._stop)
            else:
                try:
                    self._queue.put_nowait(self._stop)
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._queue.put_nowait(self._stop)
                    except queue.Full:
                        pass
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.2)

    def _run(self):
        for item in iter(self._queue.get, self._stop):
            callback, msg = item
            try:
                if msg is None:
                    callback()
                else:
                    callback(msg)
            except (Exception, asyncio.CancelledError):
                pass

    @property
    def drop_count(self) -> int:
        with self._lock:
            return self._drop_count
