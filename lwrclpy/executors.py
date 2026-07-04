import asyncio
import functools
import inspect
import logging
import multiprocessing
import threading
import time
import traceback
from typing import Iterable, Optional, List
from collections import deque
from ._async import run_coroutine
from .context import ok
from .future import Future


_logger = logging.getLogger(__name__)


class _ExecutorWakeEvent:
    """Event-like wake primitive that lets workers wait for a new wake."""

    def __init__(self):
        self._condition = threading.Condition()
        self._generation = 0

    def set(self):
        with self._condition:
            self._generation += 1
            self._condition.notify_all()

    def clear(self):
        # Kept for Event API compatibility.  Wakes are generation based, so
        # there is no sticky state to clear.
        return None

    def generation(self) -> int:
        with self._condition:
            return self._generation

    def wait(self, timeout: Optional[float] = None, *, since: Optional[int] = None) -> bool:
        with self._condition:
            if since is None:
                since = self._generation
            if self._generation != since:
                return True
            self._condition.wait(timeout)
            return self._generation != since


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
        self._wake_event = _ExecutorWakeEvent()
        self._shutdown_event = threading.Event()
        self._task_queue = deque()
        self._task_queue_lock = threading.Lock()

    def add_node(self, node):
        with self._nodes_lock:
            if node not in self._nodes:
                self._nodes.append(node)
                # Give the node a reference to our wake event so that
                # _enqueue_callback can wake us immediately.  Do not steal the
                # wake event from another executor already spinning this node
                # (e.g. a throwaway executor made by module-level spin_once).
                if getattr(node, "_executor_wake_event", None) is None:
                    node._executor_wake_event = self._wake_event
                self._wake_event.set()

    def remove_node(self, node):
        with self._nodes_lock:
            if node in self._nodes:
                self._nodes.remove(node)
                if getattr(node, "_executor_wake_event", None) is self._wake_event:
                    node._executor_wake_event = None

    def get_nodes(self) -> List:
        """Return a copy of the nodes list (thread-safe)."""
        with self._nodes_lock:
            return list(self._nodes)

    def spin(self):
        try:
            while ok() and not self._is_stopped():
                self._spin_once_impl(0.01)
        except KeyboardInterrupt:
            pass  # Graceful shutdown on SIGINT
        # Gracefully exit when shutdown() was called; do not raise.

    def spin_once(self, timeout_sec: Optional[float] = None):
        self._spin_once_impl(timeout_sec)

    def _spin_once_impl(self, timeout_sec: Optional[float] = None) -> bool:
        try:
            handler, _group, _node = self.wait_for_ready_callbacks(timeout_sec=timeout_sec)
        except StopIteration:
            return False
        try:
            handler()
        except Exception:
            _logger.exception("Unhandled exception while executing callback")
        return True

    def spin_some(self, timeout_sec: Optional[float] = None):
        self._spin_some_impl(timeout_sec)

    def _spin_some_impl(self, timeout_sec: Optional[float] = None) -> bool:
        if not ok() or self._is_stopped():
            return False
        nodes = self.get_nodes()
        ran = self._process_all_ready(nodes)
        if timeout_sec:
            time.sleep(min(timeout_sec, 0.001))
        return ran

    def shutdown(self, timeout_sec: Optional[float] = None):
        with self._stopped_lock:
            self._stopped = True
        self._wake_event.set()
        self._shutdown_event.set()
        with self._task_queue_lock:
            queued_tasks = list(self._task_queue)
            self._task_queue.clear()
        for _cb, _msg, _node, future in queued_tasks:
            if future is not None and not future.done():
                future.cancel()
        # Disconnect our wake event from nodes (leave other executors' intact)
        with self._nodes_lock:
            for node in self._nodes:
                if getattr(node, "_executor_wake_event", None) is self._wake_event:
                    node._executor_wake_event = None

    def _is_stopped(self) -> bool:
        with self._stopped_lock:
            return self._stopped

    def wake(self):
        """Wake the executor from any wait."""
        self._wake_event.set()

    def create_task(self, callback, *args, **kwargs):
        """Queue a callback for executor execution and return a Future.

        Returns an lwrclpy Future (rclpy.task.Future compatible) so it works
        with spin_until_future_complete, add_done_callback, and await.
        """
        task = functools.partial(callback, *args, **kwargs)
        future = Future()
        if self._is_stopped():
            future.cancel()
            return future
        with self._task_queue_lock:
            if self._is_stopped():
                future.cancel()
                return future
            self._task_queue.append((task, None, None, future))
        self._wake_event.set()
        return future

    def _pop_executor_task(self):
        with self._task_queue_lock:
            try:
                return self._task_queue.popleft()
            except IndexError:
                return None

    def _has_executor_tasks(self) -> bool:
        with self._task_queue_lock:
            return bool(self._task_queue)

    def wait_for_ready_callbacks(self, timeout_sec: Optional[float] = None):
        task = self._pop_executor_task()
        if task:
            cb, msg, node, future = task
            return (lambda: _execute_callback(cb, msg, future=future), None, node)
        nodes = self.get_nodes()
        item = _pop_any_callback(nodes, timeout_sec, self._is_stopped, self._wake_event)
        if not item:
            raise StopIteration()
        cb, msg, node, entity, group = item
        return (lambda: _execute_callback(cb, msg, node=node, entity=entity, group=group), group, node)

    def _process_all_ready(self, nodes: Iterable):
        ran = False
        for node in list(nodes):
            while True:
                try:
                    item = node._pop_callback()
                except Exception:
                    item = None
                if not item:
                    break
                cb, msg, entity, group = _normalize_node_callback_item(item)
                _execute_callback(cb, msg, node=node, entity=entity, group=group)
                ran = True
        return ran


class SingleThreadedExecutor(Executor):
    """Runs callbacks sequentially in the calling thread."""

    def __init__(self):
        super().__init__()


class MultiThreadedExecutor(Executor):
    """Processes callbacks concurrently on worker threads."""

    def __init__(
        self,
        num_threads: Optional[int] = None,
        *,
        context=None,
    ):
        del context  # compatibility placeholder
        super().__init__()
        self._threads: List[threading.Thread] = []
        self._num_threads = num_threads
        self._threads_lock = threading.Lock()

    def spin(self):
        if self._is_stopped():
            return
        with self._threads_lock:
            # rclpy defaults to the CPU count; sizing by node count would give
            # a single thread for the common one-node case and deadlock
            # nested-callback patterns that rely on parallel workers.
            try:
                default_threads = multiprocessing.cpu_count()
            except Exception:
                default_threads = 2
            thread_count = self._num_threads or max(2, default_threads)
            if thread_count <= 0:
                thread_count = 1
            for _ in range(thread_count):
                t = threading.Thread(target=self._worker, daemon=True)
                t.start()
                self._threads.append(t)
        try:
            while ok() and not self._is_stopped():
                # Workers own callback processing and the work wake event.
                # The spin thread only waits for shutdown/external shutdown.
                self._shutdown_event.wait(timeout=0.5)
            if not ok() and not self._is_stopped():
                raise ExternalShutdownException()
        except KeyboardInterrupt:
            pass  # Graceful shutdown on SIGINT
        finally:
            self.shutdown()

    def _worker(self):
        while ok() and not self._is_stopped():
            task = self._pop_executor_task()
            if task is not None:
                cb, msg, _node, future = task
                _execute_callback(cb, msg, future=future)
                continue
            nodes = self.get_nodes()
            item = _pop_any_callback(nodes, 0.05, self._is_stopped, self._wake_event)
            if item:
                cb, msg, node, entity, group = item
                _execute_callback(cb, msg, node=node, entity=entity, group=group)

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
        except KeyboardInterrupt:
            pass  # Graceful shutdown on SIGINT
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
        except KeyboardInterrupt:
            pass  # Graceful shutdown on SIGINT
        finally:
            if added:
                executor.remove_node(node)


def spin_once(node, timeout_sec: Optional[float] = None):
    exec_obj = SingleThreadedExecutor()
    added = False
    try:
        if node not in exec_obj.get_nodes():
            exec_obj.add_node(node)
            added = True
        exec_obj.spin_once(timeout_sec)
    finally:
        if added:
            exec_obj.remove_node(node)
        exec_obj.shutdown()


def spin_some(node, timeout_sec: Optional[float] = None):
    exec_obj = SingleThreadedExecutor()
    added = False
    try:
        if node not in exec_obj.get_nodes():
            exec_obj.add_node(node)
            added = True
        deadline = None
        if timeout_sec is not None and timeout_sec > 0:
            deadline = time.monotonic() + timeout_sec
        while True:
            remaining = 0.0
            if deadline is not None:
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
            ran = exec_obj._spin_once_impl(remaining if deadline is not None else 0.0)
            if not ran:
                return
    finally:
        if added:
            exec_obj.remove_node(node)
        exec_obj.shutdown()


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
            exec_obj._spin_once_impl(0.01)
            if timeout_sec is not None and (time.monotonic() - start) >= timeout_sec:
                return False
    except KeyboardInterrupt:
        return False  # Graceful shutdown on SIGINT
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
    for item in callbacks:
        cb, msg, entity, group = _normalize_node_callback_item(item)
        _execute_callback(cb, msg, node=node, entity=entity, group=group)
    return bool(callbacks)


def _normalize_node_callback_item(item):
    if len(item) == 4:
        return item
    if len(item) == 3:
        cb, msg, entity = item
        return cb, msg, entity, None
    cb, msg = item
    return cb, msg, None, None


def _execute_callback(cb, msg, future=None, *, node=None, entity=None, group=None):
    if future is not None and future.cancelled():
        return None
    try:
        try:
            result = _invoke_callback(cb, msg)
        except (Exception, asyncio.CancelledError) as exc:
            if future is not None and not future.done():
                future.set_exception(exc)
            else:
                traceback.print_exception(type(exc), exc, exc.__traceback__)
            return None
        if future is not None and not future.done():
            future.set_result(result)
        return result
    finally:
        if node is not None and entity is not None and group is not None:
            end_callback = getattr(node, "_end_callback_execution", None)
            if callable(end_callback):
                end_callback(entity, group)


def _invoke_callback(cb, msg):
    result = cb(msg) if msg is not None else cb()
    if inspect.iscoroutine(result):
        return run_coroutine(result)
    return result


def _pop_any_callback(nodes: Iterable, timeout_sec: Optional[float], is_stopped_fn, wake_event: Optional[threading.Event] = None):
    """Pop a callback from any node's queue, with event-driven waking.

    Instead of busy-polling with 1ms sleeps, we wait on the wake_event
    which is set by Node._enqueue_callback when new work arrives.
    """
    start = time.monotonic()

    # Cache the stopped check callable
    _check_stopped = is_stopped_fn if callable(is_stopped_fn) else (lambda: is_stopped_fn)

    if not ok() or _check_stopped():
        return None

    while True:
        wake_generation = None
        get_generation = getattr(wake_event, "generation", None) if wake_event is not None else None
        if callable(get_generation):
            wake_generation = get_generation()

        # Check all nodes for ready callbacks
        for node in nodes:
            try:
                item = node._pop_callback()
            except Exception:
                continue
            if item:
                cb, msg, entity, group = _normalize_node_callback_item(item)
                return (cb, msg, node, entity, group)

        # Check stop conditions before sleeping
        if not ok() or _check_stopped():
            return None

        # Check timeout
        if timeout_sec is not None:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_sec:
                return None
            remaining = timeout_sec - elapsed
        else:
            remaining = 0.05  # 50ms default poll interval when no timeout

        # Wait for wake event with up to 50ms cap.  Generation-aware waits
        # avoid both sticky-event busy loops and lost wake-ups between the
        # queue scan and the wait call.
        wait_time = min(remaining, 0.05)
        if wake_event:
            if wake_generation is None:
                wake_event.wait(wait_time)
            else:
                wake_event.wait(wait_time, since=wake_generation)
        else:
            time.sleep(wait_time)
