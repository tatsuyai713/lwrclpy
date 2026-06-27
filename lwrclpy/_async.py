import asyncio
import atexit
import contextlib
import threading


class _AsyncRunner:
    def __init__(self):
        self._loop = None
        self._thread = None
        self._lock = threading.Lock()

    def _ensure_started(self):
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            ready = threading.Event()
            loop_holder = []

            def run_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop_holder.append(loop)
                ready.set()
                loop.run_forever()

            self._thread = threading.Thread(target=run_loop, name="lwrclpy-async-runner", daemon=True)
            self._thread.start()
            ready.wait()
            self._loop = loop_holder[0]
            return self._loop

    def run(self, coro):
        loop = self._ensure_started()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def shutdown(self):
        with self._lock:
            loop = self._loop
            thread = self._thread
            self._loop = None
            self._thread = None
        if loop is None:
            return
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and threading.current_thread() is not thread:
            thread.join(timeout=1.0)
        if not loop.is_closed():
            with contextlib.suppress(Exception):
                loop.close()


_runner = _AsyncRunner()
atexit.register(_runner.shutdown)


def run_coroutine(coro):
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None
    if running_loop is not None:
        raise RuntimeError("Cannot synchronously run coroutine callback from an active event loop")
    return _runner.run(coro)


def shutdown_async_runner():
    _runner.shutdown()
