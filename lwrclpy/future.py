import asyncio
import threading
from typing import Any, Callable, Optional, List, TypeVar, Generic

T = TypeVar('T')


class Future(Generic[T]):
    """Minimal Future compatible with rclpy.task.Future.
    
    Thread-safe implementation that supports both synchronous waiting
    and asyncio await patterns.
    """

    def __init__(self):
        self._event = threading.Event()
        self._result: Optional[T] = None
        self._exception: Optional[BaseException] = None
        self._done = False
        self._cancelled = False
        self._callbacks: List[Callable[["Future[T]"], None]] = []
        self._lock = threading.Lock()

    def done(self) -> bool:
        """Return True if the future is done (has result, exception, or cancelled)."""
        with self._lock:
            return self._done

    def cancelled(self) -> bool:
        """Return True if the future was cancelled."""
        with self._lock:
            return self._cancelled

    def running(self) -> bool:
        """Return True if the future is running (not done yet)."""
        return not self.done()

    def result(self, timeout: Optional[float] = None) -> T:
        """Wait for and return the result.
        
        Raises:
            TimeoutError: If timeout is reached before result is available.
            CancelledError: If the future was cancelled.
            Exception: If the future completed with an exception.
        """
        if not self._event.wait(timeout):
            raise TimeoutError("Future result not ready")
        with self._lock:
            if self._cancelled:
                raise asyncio.CancelledError("Future was cancelled")
            if self._exception:
                raise self._exception
            return self._result

    def exception(self, timeout: Optional[float] = None) -> Optional[BaseException]:
        """Wait for the future and return any exception.
        
        Returns None if the future completed successfully.
        """
        if not self._event.wait(timeout):
            raise TimeoutError("Future not ready")
        with self._lock:
            return self._exception

    def set_result(self, value: T) -> None:
        """Set the result of the future."""
        run_callbacks = False
        with self._lock:
            if self._done:
                return
            self._result = value
            self._done = True
            run_callbacks = True
        self._event.set()
        if run_callbacks:
            self._run_callbacks()

    def set_exception(self, exc: BaseException) -> None:
        """Set an exception as the result of the future."""
        run_callbacks = False
        with self._lock:
            if self._done:
                return
            self._exception = exc
            self._done = True
            run_callbacks = True
        self._event.set()
        if run_callbacks:
            self._run_callbacks()

    def add_done_callback(self, callback: Callable[["Future[T]"], None]) -> None:
        """Add a callback to be called when the future completes."""
        run_now = False
        with self._lock:
            if self._done:
                run_now = True
            else:
                self._callbacks.append(callback)
        if run_now:
            try:
                callback(self)
            except Exception:
                pass

    def remove_done_callback(self, callback: Callable[["Future[T]"], None]) -> int:
        """Remove a callback. Returns number of callbacks removed."""
        with self._lock:
            count = self._callbacks.count(callback)
            while callback in self._callbacks:
                self._callbacks.remove(callback)
            return count

    def _run_callbacks(self):
        """Run all registered callbacks."""
        callbacks = []
        with self._lock:
            callbacks = list(self._callbacks)
            self._callbacks.clear()
        for cb in callbacks:
            try:
                cb(self)
            except Exception:
                continue

    def cancel(self) -> bool:
        """Attempt to cancel the future.
        
        Returns True if the future was successfully cancelled.
        """
        with self._lock:
            if self._done:
                return False
            self._cancelled = True
            self._exception = asyncio.CancelledError()
            self._done = True
        self._event.set()
        self._run_callbacks()
        return True

    async def _await_impl(self) -> T:
        """Implementation for await support."""
        loop = asyncio.get_event_loop()
        
        # Create an asyncio Event for integration
        async_event = asyncio.Event()
        
        def on_done(_):
            # Schedule the event to be set in the event loop
            try:
                loop.call_soon_threadsafe(async_event.set)
            except RuntimeError:
                # Event loop might be closed
                pass
        
        # Add callback if not already done
        if not self.done():
            self.add_done_callback(on_done)
        
        # If already done, return immediately
        if self.done():
            with self._lock:
                if self._cancelled:
                    raise asyncio.CancelledError("Future was cancelled")
                if self._exception:
                    raise self._exception
                return self._result
        
        # Wait for completion
        await async_event.wait()
        
        with self._lock:
            if self._cancelled:
                raise asyncio.CancelledError("Future was cancelled")
            if self._exception:
                raise self._exception
            return self._result

    def __await__(self):
        return self._await_impl().__await__()

    def __repr__(self):
        with self._lock:
            if self._done:
                if self._cancelled:
                    return "<Future cancelled>"
                elif self._exception:
                    return f"<Future finished exception={self._exception!r}>"
                else:
                    return f"<Future finished result={self._result!r}>"
            else:
                return "<Future pending>"
