import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, List


class ClockType(Enum):
    """Clock type enumeration matching rclpy.clock.ClockType."""
    ROS_TIME = 1
    SYSTEM_TIME = 2
    STEADY_TIME = 3


@dataclass
class JumpThreshold:
    min_forward: Optional["Duration"] = None
    min_backward: Optional["Duration"] = None
    on_clock_change: bool = False


@dataclass
class TimeJump:
    clock_change: bool = False
    delta: Optional["Duration"] = None


class JumpHandle:
    def __init__(self, clock: "Clock", pre_callback=None, post_callback=None):
        self._clock = clock
        self._pre_callback = pre_callback
        self._post_callback = post_callback

    def unregister(self):
        self._clock.remove_time_jump_callback(self)

    def __call__(self, delta_ns: int):
        jump = TimeJump(delta=Duration(nanoseconds=delta_ns))
        if self._pre_callback is not None:
            self._pre_callback(jump)
        if self._post_callback is not None:
            self._post_callback(jump)


class Time:
    """Represents a point in time."""
    
    __slots__ = ("_nanoseconds", "_clock_type")
    
    def __init__(self, *, seconds: float = 0.0, nanoseconds: int = 0, clock_type: ClockType = ClockType.SYSTEM_TIME):
        total_ns = int(nanoseconds)
        total_ns += int(seconds * 1_000_000_000)
        self._nanoseconds = total_ns
        self._clock_type = clock_type

    @property
    def nanoseconds(self) -> int:
        return self._nanoseconds

    @property
    def seconds_nanoseconds(self) -> tuple:
        """Return (seconds, nanoseconds) tuple."""
        return (self._nanoseconds // 1_000_000_000, self._nanoseconds % 1_000_000_000)

    @property
    def clock_type(self) -> ClockType:
        return self._clock_type

    def to_msg(self):
        """Convert to builtin_interfaces/Time message."""
        try:
            from builtin_interfaces.msg import Time as TimeMsg
            msg = TimeMsg()
            msg.sec = self._nanoseconds // 1_000_000_000
            msg.nanosec = self._nanoseconds % 1_000_000_000
            return msg
        except Exception:
            return None

    @classmethod
    def from_msg(cls, msg, clock_type: ClockType = ClockType.ROS_TIME) -> "Time":
        """Create Time from builtin_interfaces/Time message."""
        sec = getattr(msg, "sec", 0)
        nanosec = getattr(msg, "nanosec", 0)
        return cls(seconds=sec, nanoseconds=nanosec, clock_type=clock_type)

    def __eq__(self, other):
        if not isinstance(other, Time):
            return NotImplemented
        return self._nanoseconds == other._nanoseconds

    def __ne__(self, other):
        if not isinstance(other, Time):
            return NotImplemented
        return self._nanoseconds != other._nanoseconds

    def __lt__(self, other):
        if not isinstance(other, Time):
            return NotImplemented
        return self._nanoseconds < other._nanoseconds

    def __le__(self, other):
        if not isinstance(other, Time):
            return NotImplemented
        return self._nanoseconds <= other._nanoseconds

    def __gt__(self, other):
        if not isinstance(other, Time):
            return NotImplemented
        return self._nanoseconds > other._nanoseconds

    def __ge__(self, other):
        if not isinstance(other, Time):
            return NotImplemented
        return self._nanoseconds >= other._nanoseconds

    def __sub__(self, other):
        if isinstance(other, Time):
            from .duration import Duration
            return Duration(nanoseconds=self._nanoseconds - other._nanoseconds)
        if isinstance(other, Duration):
            return Time(nanoseconds=self._nanoseconds - other.nanoseconds, clock_type=self._clock_type)
        return NotImplemented

    def __add__(self, other):
        from .duration import Duration
        if isinstance(other, Duration):
            return Time(nanoseconds=self._nanoseconds + other.nanoseconds, clock_type=self._clock_type)
        return NotImplemented

    def __repr__(self):
        sec, nsec = self.seconds_nanoseconds
        return f"Time(seconds={sec}, nanoseconds={nsec}, clock_type={self._clock_type.name})"


# Alias for backward compatibility
_TimePoint = Time

# Import Duration from the duration module to ensure consistency
from .duration import Duration


_SLEEP_CHECK_INTERVAL_SEC = 0.1


def _context_ok() -> bool:
    try:
        from .context import is_shutdown
        return not is_shutdown()
    except Exception:
        return True


def _sleep_seconds(seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(seconds))
    try:
        while True:
            if not _context_ok():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, _SLEEP_CHECK_INTERVAL_SEC))
    except KeyboardInterrupt:
        return False


class Clock:
    """Time provider similar to rclpy.clock.Clock.
    
    Supports system time, steady time, and simulated time for testing.
    """

    def __init__(self, *, clock_type: ClockType = ClockType.SYSTEM_TIME):
        self._clock_type = clock_type
        self._lock = threading.Lock()
        self._time_update_condition = threading.Condition(self._lock)
        self._ros_time_override: Optional[int] = None
        self._ros_time_is_active = False
        self._time_jump_callbacks: List[Callable] = []

    @property
    def clock_type(self) -> ClockType:
        return self._clock_type

    @property
    def ros_time_is_active(self) -> bool:
        """Return True if ROS time override is active."""
        with self._lock:
            return self._ros_time_is_active

    def now(self) -> Time:
        """Return the current time."""
        with self._lock:
            if self._clock_type == ClockType.ROS_TIME and self._ros_time_is_active and self._ros_time_override is not None:
                return Time(nanoseconds=self._ros_time_override, clock_type=ClockType.ROS_TIME)
        
        if self._clock_type == ClockType.STEADY_TIME:
            # Use monotonic clock for steady time
            ns = time.monotonic_ns()
            return Time(nanoseconds=ns, clock_type=ClockType.STEADY_TIME)
        else:
            # System time or ROS time (when not overridden)
            ns = time.time_ns()
            return Time(nanoseconds=ns, clock_type=self._clock_type)

    def set_ros_time_override(self, time_point: Time):
        """Set ROS time override for simulation."""
        with self._lock:
            old_time = self._ros_time_override
            self._ros_time_override = time_point.nanoseconds
            self._ros_time_is_active = True
            callbacks = list(self._time_jump_callbacks) if old_time is not None else []
            self._time_update_condition.notify_all()
        # Invoke jump callbacks outside the lock: a callback that reads the
        # clock or unregisters itself would otherwise deadlock on self._lock.
        if callbacks:
            delta = time_point.nanoseconds - old_time
            for cb in callbacks:
                try:
                    cb(delta)
                except Exception:
                    pass

    def clear_ros_time_override(self):
        """Clear ROS time override."""
        with self._lock:
            self._ros_time_override = None
            self._ros_time_is_active = False
            self._time_update_condition.notify_all()

    def add_time_jump_callback(self, callback: Callable[[int], None]):
        """Add a callback to be notified of time jumps (delta in nanoseconds)."""
        with self._lock:
            self._time_jump_callbacks.append(callback)

    def create_jump_callback(self, threshold: JumpThreshold, pre_callback=None, post_callback=None) -> JumpHandle:
        del threshold
        handle = JumpHandle(self, pre_callback=pre_callback, post_callback=post_callback)
        self.add_time_jump_callback(handle)
        return handle

    def remove_time_jump_callback(self, callback: Callable[[int], None]):
        """Remove a time jump callback."""
        with self._lock:
            if callback in self._time_jump_callbacks:
                self._time_jump_callbacks.remove(callback)

    def _ros_override_active(self) -> bool:
        with self._lock:
            return (
                self._clock_type == ClockType.ROS_TIME
                and self._ros_time_is_active
                and self._ros_time_override is not None
            )

    def sleep_until(self, until: Time) -> bool:
        """Sleep until the specified time on this clock's time base.

        For a ROS_TIME clock with an active override this waits for the
        simulated time to reach *until* (woken by set_ros_time_override),
        matching rclpy semantics instead of sleeping wall-clock time.
        Returns True if sleep completed, False if interrupted.
        """
        try:
            while True:
                if not _context_ok():
                    return False
                now = self.now()
                if now.nanoseconds >= until.nanoseconds:
                    return True
                if self._ros_override_active():
                    with self._time_update_condition:
                        self._time_update_condition.wait(_SLEEP_CHECK_INTERVAL_SEC)
                else:
                    remaining = (until.nanoseconds - now.nanoseconds) / 1_000_000_000
                    time.sleep(min(remaining, _SLEEP_CHECK_INTERVAL_SEC))
        except KeyboardInterrupt:
            return False

    def sleep_for(self, duration: Duration) -> bool:
        """Sleep for the specified duration on this clock's time base.

        Returns True if sleep completed, False if interrupted.
        """
        now = self.now()
        until = Time(nanoseconds=now.nanoseconds + duration.nanoseconds, clock_type=now.clock_type)
        return self.sleep_until(until)
