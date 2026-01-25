import time
import threading
from enum import Enum
from typing import Optional, Callable, List


class ClockType(Enum):
    """Clock type enumeration matching rclpy.clock.ClockType."""
    ROS_TIME = 1
    SYSTEM_TIME = 2
    STEADY_TIME = 3


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


class Clock:
    """Time provider similar to rclpy.clock.Clock.
    
    Supports system time, steady time, and simulated time for testing.
    """

    def __init__(self, *, clock_type: ClockType = ClockType.SYSTEM_TIME):
        self._clock_type = clock_type
        self._lock = threading.Lock()
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
            
            # Notify time jump callbacks
            if old_time is not None:
                delta = time_point.nanoseconds - old_time
                for cb in self._time_jump_callbacks:
                    try:
                        cb(delta)
                    except Exception:
                        pass

    def clear_ros_time_override(self):
        """Clear ROS time override."""
        with self._lock:
            self._ros_time_override = None
            self._ros_time_is_active = False

    def add_time_jump_callback(self, callback: Callable[[int], None]):
        """Add a callback to be notified of time jumps (delta in nanoseconds)."""
        with self._lock:
            self._time_jump_callbacks.append(callback)

    def remove_time_jump_callback(self, callback: Callable[[int], None]):
        """Remove a time jump callback."""
        with self._lock:
            if callback in self._time_jump_callbacks:
                self._time_jump_callbacks.remove(callback)

    def sleep_until(self, until: Time) -> bool:
        """Sleep until the specified time.
        
        Returns True if sleep completed, False if interrupted.
        """
        now = self.now()
        if until <= now:
            return True
        
        duration_ns = until.nanoseconds - now.nanoseconds
        time.sleep(duration_ns / 1_000_000_000)
        return True

    def sleep_for(self, duration: Duration) -> bool:
        """Sleep for the specified duration.
        
        Returns True if sleep completed, False if interrupted.
        """
        time.sleep(duration.nanoseconds / 1_000_000_000)
        return True
