import asyncio
import inspect
import threading
import time
from typing import Iterable, Optional, List
from collections import deque
from .context import ok


class ExternalShutdownException(RuntimeError):
    """Raised when spin exits because the context was shutdown externally."""


class Executor:
    """Base executor compatible with rclpy's Executor surface.
    
    Thread-safe implementation with proper locking for concurrent access.
    """

    def __init__(self):
        self._nodes: List = []
        self._nodes_lock = threading.RLock()
        self._stopped = False
        self._stopped_lock = threading.Lock()
        self._wake_event = threading.Event()

    def add_node(self, node):
        with self._nodes_lock:
            if node not in self._nodes:
                self._nodes.append(node)
                self._wake_event.set()

    def remove_node(self, node):
        with self._nodes_lock:
            if node in self._nodes:
                self._nodes.remove(node)

    def get_nodes(self) -> List:
        """Return a copy of the nodes list (thread-safe)."""
        with self._nodes_lock:
            return list(self._nodes)

    def spin(self):
        while ok() and not self._is_stopped():
            self.spin_once(0.01)
        # Gracefully exit when shutdown() was called; do not raise.

    def spin_once(self, timeout_sec: Optional[float] = None):
        try:
            handler, _group, _node = self.wait_for_ready_callbacks(timeout_sec=timeout_sec)
        except StopIteration:
            return
        try:
            handler()
        except Exception:
            pass

    def spin_some(self, timeout_sec: Optional[float] = None):
        if not ok() or self._is_stopped():
            return
        nodes = self.get_nodes()
        self._process_all_ready(nodes)
        if timeout_sec:
            time.sleep(min(timeout_sec, 0.001))

    def shutdown(self, timeout_sec: Optional[float] = None):
        with self._stopped_lock:
            self._stopped = True
        self._wake_event.set()

    def _is_stopped(self) -> bool:
        with self._stopped_lock:
            return self._stopped

    def wake(self):
        """Wake the executor from any wait."""
        self._wake_event.set()

    def wait_for_ready_callbacks(self, timeout_sec: Optional[float] = None):
        nodes = self.get_nodes()
        item = _pop_any_callback(nodes, timeout_sec, self._is_stopped, self._wake_event)
        if not item:
            raise StopIteration()
        cb, msg, node = item
        return (lambda: _invoke_callback(cb, msg), None, node)

    def _process_all_ready(self, nodes: Iterable):
        for node in list(nodes):
            while True:
                try:
                    item = node._pop_callback()
                except Exception:
                    item = None
                if not item:
                    break
                cb, msg = item
                _invoke_callback(cb, msg)


class SingleThreadedExecutor(Executor):
    """Runs callbacks sequentially in the calling thread."""

    def __init__(self):
        super().__init__()


class MultiThreadedExecutor(Executor):
    """Processes callbacks across a thread pool with proper synchronization."""

    def __init__(self, num_threads: Optional[int] = None):
        super().__init__()
        self._threads: List[threading.Thread] = []
        self._num_threads = num_threads
        self._threads_lock = threading.Lock()
        self._callback_lock = threading.Lock()

    def spin(self):
        if self._is_stopped():
            return
        with self._threads_lock:
            thread_count = self._num_threads or max(1, len(self.get_nodes()))
            if thread_count <= 0:
                thread_count = 1
            for _ in range(thread_count):
                t = threading.Thread(target=self._worker, daemon=True)
                t.start()
                self._threads.append(t)
        try:
            while ok() and not self._is_stopped():
                nodes = self.get_nodes()
                if not any(getattr(n, "_has_pending_work", lambda: True)() for n in nodes):
                    # Wait for wake event or timeout
                    self._wake_event.wait(timeout=0.01)
                    self._wake_event.clear()
                    continue
                time.sleep(0.01)
            if not ok() and not self._is_stopped():
                raise ExternalShutdownException()
        finally:
            self.shutdown()

    def _worker(self):
        while ok() and not self._is_stopped():
            nodes = self.get_nodes()
            item = _pop_any_callback(nodes, 0.01, self._is_stopped, self._wake_event)
            if item:
                cb, msg, _node = item
                with self._callback_lock:
                    _invoke_callback(cb, msg)

    def shutdown(self, timeout_sec: Optional[float] = None):
        super().shutdown(timeout_sec)
        with self._threads_lock:
            for t in self._threads:
                t.join(timeout=timeout_sec or 0.1)
            self._threads.clear()


def spin(node, executor: Optional[Executor] = None):
    if executor is None:
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        try:
            executor.spin()
        finally:
            executor.remove_node(node)
            executor.shutdown()
    else:
        added = False
        if node not in executor.get_nodes():
            executor.add_node(node)
            added = True
        try:
            executor.spin()
        finally:
            if added:
                executor.remove_node(node)


def spin_once(node, timeout_sec: Optional[float] = None):
    _run_callbacks_for_node(node)
    if timeout_sec:
        time.sleep(min(timeout_sec, 0.001))


def spin_some(node, timeout_sec: Optional[float] = None):
    _run_callbacks_for_node(node)
    if timeout_sec:
        time.sleep(min(timeout_sec, 0.001))


def spin_until_future_complete(node, future, timeout_sec: Optional[float] = None, *, executor: Optional[Executor] = None):
    start = time.monotonic()
    own_executor = executor is None
    exec_obj = executor or SingleThreadedExecutor()
    added = False
    if node not in exec_obj.get_nodes():
        exec_obj.add_node(node)
        added = True
    try:
        while ok():
            if future.done():
                return True
            exec_obj.spin_once(0.01)
            if timeout_sec is not None and (time.monotonic() - start) >= timeout_sec:
                return False
    finally:
        if added:
            exec_obj.remove_node(node)
        if own_executor:
            exec_obj.shutdown()
    return False


def _run_callbacks_for_node(node):
    try:
        callbacks = node._drain_callbacks()
    except Exception:
        callbacks = []
    for cb, msg in callbacks:
        _invoke_callback(cb, msg)


def _invoke_callback(cb, msg):
    try:
        result = cb(msg) if msg is not None else cb()
        if inspect.iscoroutine(result):
            asyncio.run(result)
    except Exception:
        pass


def _pop_any_callback(nodes: Iterable, timeout_sec: Optional[float], is_stopped_fn, wake_event: Optional[threading.Event] = None):
    """Pop a callback from any node's queue, with proper timeout handling."""
    start = time.monotonic()
    while ok() and not (is_stopped_fn() if callable(is_stopped_fn) else is_stopped_fn):
        for node in list(nodes):
            try:
                item = node._pop_callback()
            except Exception:
                item = None
            if item:
                cb, msg = item
                return (cb, msg, node)
        
        # Check timeout
        if timeout_sec is None:
            if wake_event:
                wake_event.wait(0.001)
                wake_event.clear()
            else:
                time.sleep(0.001)
            continue
        
        elapsed = time.monotonic() - start
        if elapsed >= max(timeout_sec, 0):
            return None
        
        # Wait with event or sleep
        remaining = max(0.001, timeout_sec - elapsed)
        if wake_event:
            wake_event.wait(min(remaining, 0.001))
            wake_event.clear()
        else:
            time.sleep(min(remaining, 0.001))
    return None
