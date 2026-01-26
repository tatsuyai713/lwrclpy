import threading
import time
from typing import Optional, Callable


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
        self._start_time = time.monotonic()
        self._next_t = self._start_time + self._period
        self._last_call: Optional[float] = None
        self._call_count = 0

    def start(self):
        """Start the timer thread."""
        with self._lock:
            if self._thr is not None and self._thr.is_alive():
                return
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
            
            # Fire the callback
            try:
                self._last_call = time.monotonic()
                self._call_count += 1
                if self._enqueue_cb is not None:
                    # Enqueue the user callback to be run by the executor
                    self._enqueue_cb(self._callback, None)
                else:
                    self._callback()
            except Exception:
                pass  # Swallow callback exceptions
            finally:
                if self._oneshot:
                    self._stop.set()
                    break
                
                # Calculate next fire time with drift compensation
                # Use the scheduled time as base, not the actual execution time
                # This prevents drift accumulation
                now = time.monotonic()
                self._next_t += self._period
                
                # If we've fallen behind by more than one period, 
                # reset to prevent catching up
                if self._next_t < now:
                    # Skip missed intervals
                    missed = int((now - self._next_t) / self._period) + 1
                    self._next_t += missed * self._period

    def cancel(self):
        """Request stop and join from external threads; skip join when self-canceling."""
        self._stop.set()
        # Avoid joining the current thread (raises RuntimeError)
        with self._lock:
            thr = self._thr
        if thr is not None and threading.current_thread() is not thr:
            thr.join(timeout=1)

    def reset(self):
        """Reset next wake-up to now + period."""
        with self._lock:
            self._next_t = time.monotonic() + self._period

    def is_canceled(self) -> bool:
        """Return True if the timer has been canceled."""
        return self._stop.is_set()

    def is_ready(self) -> bool:
        """Return True if the timer is ready to fire (past scheduled time)."""
        if self._stop.is_set():
            return False
        return time.monotonic() >= self._next_t

    def time_until_next_call(self) -> float:
        """Return seconds until next scheduled call (0 if past due)."""
        return max(0.0, self._next_t - time.monotonic())

    def time_since_last_call(self) -> Optional[float]:
        """Return seconds since last callback execution, or None if never called."""
        if self._last_call is None:
            return None
        return time.monotonic() - self._last_call

    @property
    def timer_period_ns(self) -> int:
        """Return the timer period in nanoseconds."""
        return int(self._period * 1_000_000_000)

    @property
    def call_count(self) -> int:
        """Return the number of times the callback has been invoked."""
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
