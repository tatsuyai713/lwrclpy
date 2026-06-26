import asyncio
import logging
import threading
import time
from typing import Optional, Callable


_logger = logging.getLogger(__name__)


class _RepeatingTimer:
    """Lightweight repeating/oneshot timer similar to rclpy.Timer.
    
    Features:
    - Accurate drift compensation using monotonic clock
    - Supports oneshot mode
    - Can enqueue callbacks to executor or call directly
    - Thread-safe cancel/reset operations
    """

    def __init__(self, period_sec: float, callback: Callable, *, oneshot: bool = False, enqueue_cb=None):
        if period_sec <= 0:
            raise ValueError("Timer period must be positive")
        self._period = float(period_sec)
        self._callback = callback
        self._oneshot = oneshot
        self._enqueue_cb = enqueue_cb
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._start_time = time.monotonic()
        self._next_t = self._start_time + self._period
        self._last_call: Optional[float] = None
        self._call_count = 0
        self._callback_pending = False
        self._canceled = False

    def start(self):
        """Start the timer thread."""
        with self._lock:
            if self._thr is not None and self._thr.is_alive():
                return
            self._canceled = False
            self._stop.clear()
            self._start_time = time.monotonic()
            self._next_t = self._start_time + self._period
            self._thr = threading.Thread(target=self._run, daemon=True)
            self._thr.start()

    def _run(self):
        """Timer thread main loop with accurate drift compensation."""
        while not self._stop.is_set():
            now = time.monotonic()
            sleep = self._next_t - now
            
            if sleep > 0:
                # Wait until next fire time or stop event
                if self._stop.wait(sleep):
                    break
            
            if self._stop.is_set():
                break
            
            # Fire or enqueue the callback.  When executor-driven, keep at
            # most one outstanding callback so slow executors do not build an
            # unbounded backlog of stale timer events.
            try:
                if self._enqueue_cb is not None:
                    if not self._mark_callback_pending():
                        continue
                    self._enqueue_cb(self._run_queued_callback, None)
                else:
                    with self._lock:
                        self._last_call = time.monotonic()
                        self._call_count += 1
                    self._callback()
            except asyncio.CancelledError:
                if self._enqueue_cb is not None:
                    self._clear_callback_pending()
            except Exception:
                if self._enqueue_cb is not None:
                    self._clear_callback_pending()
                else:
                    _logger.exception("Timer callback failed")
            finally:
                if self._oneshot:
                    self._stop.set()
                else:
                    # Calculate next fire time with drift compensation.  Use
                    # the scheduled time as base, not actual execution time.
                    now = time.monotonic()
                    self._next_t += self._period

                    # If we've fallen behind by more than one period, skip
                    # missed intervals instead of catching up in a burst.
                    if self._next_t < now:
                        missed = int((now - self._next_t) / self._period) + 1
                        self._next_t += missed * self._period

    def _mark_callback_pending(self) -> bool:
        with self._pending_lock:
            if self._callback_pending:
                return False
            self._callback_pending = True
            return True

    def _clear_callback_pending(self) -> None:
        with self._pending_lock:
            self._callback_pending = False

    def _run_queued_callback(self, _msg=None):
        try:
            with self._lock:
                if self._canceled:
                    return
                self._last_call = time.monotonic()
                self._call_count += 1
            self._callback()
        finally:
            self._clear_callback_pending()

    def cancel(self):
        """Request stop and join from external threads; skip join when self-canceling."""
        with self._lock:
            self._canceled = True
            self._stop.set()
            thr = self._thr
        self._clear_callback_pending()
        # Avoid joining the current thread (raises RuntimeError)
        if thr is not None and threading.current_thread() is not thr:
            thr.join(timeout=1)

    def reset(self):
        """Reset next wake-up to now + period."""
        restart = False
        with self._lock:
            self._canceled = False
            self._stop.clear()
            self._next_t = time.monotonic() + self._period
            if self._thr is None or not self._thr.is_alive():
                restart = True
                self._thr = threading.Thread(target=self._run, daemon=True)
                self._thr.start()
        if restart:
            self._clear_callback_pending()

    def is_canceled(self) -> bool:
        """Return True if the timer has been canceled."""
        with self._lock:
            return self._canceled

    def is_ready(self) -> bool:
        """Return True if the timer is ready to fire (past scheduled time)."""
        with self._lock:
            if self._canceled or self._stop.is_set():
                return False
            next_t = self._next_t
        return time.monotonic() >= next_t

    def time_until_next_call(self) -> float:
        """Return seconds until next scheduled call (0 if past due)."""
        with self._lock:
            next_t = self._next_t
        return max(0.0, next_t - time.monotonic())

    def time_since_last_call(self) -> Optional[float]:
        """Return seconds since last callback execution, or None if never called."""
        with self._lock:
            last_call = self._last_call
        if last_call is None:
            return None
        return time.monotonic() - last_call

    @property
    def timer_period_ns(self) -> int:
        """Return the timer period in nanoseconds."""
        return int(self._period * 1_000_000_000)

    @property
    def call_count(self) -> int:
        """Return the number of times the callback has been invoked."""
        with self._lock:
            return self._call_count


def create_timer(period_sec: float, callback: Callable, *, oneshot: bool = False, enqueue_cb=None) -> _RepeatingTimer:
    """
    Create a repeating or oneshot timer.
    
    Args:
        period_sec: Timer period in seconds (must be positive)
        callback: Function to call when timer fires
        oneshot: If True, timer fires only once
        enqueue_cb: If provided, callbacks are queued (cb, msg) style 
                    instead of invoked in the timer thread
    
    Returns:
        A started timer instance
    """
    t = _RepeatingTimer(period_sec, callback, oneshot=oneshot, enqueue_cb=enqueue_cb)
    t.start()
    return t


# Alias for rclpy compatibility
Timer = _RepeatingTimer
