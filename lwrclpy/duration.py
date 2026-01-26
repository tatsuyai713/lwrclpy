class Duration:
    """Simple duration helper mirroring rclpy.duration.Duration for sample compatibility.
    
    Note: A more complete Duration implementation is in clock.py. This module
    exists for backward compatibility with imports like `from lwrclpy.duration import Duration`.
    """

    __slots__ = ("_nanoseconds",)

    def __init__(self, *, seconds: float = 0.0, nanoseconds: int = 0):
        total_ns = int(nanoseconds)
        total_ns += int(seconds * 1_000_000_000)
        self._nanoseconds = total_ns

    @property
    def nanoseconds(self) -> int:
        return self._nanoseconds

    def seconds(self) -> float:
        """Return duration as floating point seconds."""
        return self._nanoseconds / 1_000_000_000

    def to_msg(self):
        """Convert to builtin_interfaces/Duration message."""
        try:
            from builtin_interfaces.msg import Duration as DurationMsg  # type: ignore

            msg = DurationMsg()
            msg.sec = self._nanoseconds // 1_000_000_000
            msg.nanosec = self._nanoseconds % 1_000_000_000
            return msg
        except Exception:
            return None

    @classmethod
    def from_msg(cls, msg) -> "Duration":
        """Create Duration from builtin_interfaces/Duration message."""
        sec = getattr(msg, "sec", 0)
        nanosec = getattr(msg, "nanosec", 0)
        return cls(seconds=sec, nanoseconds=nanosec)

    def __eq__(self, other):
        if not isinstance(other, Duration):
            return NotImplemented
        return self._nanoseconds == other._nanoseconds

    def __ne__(self, other):
        if not isinstance(other, Duration):
            return NotImplemented
        return self._nanoseconds != other._nanoseconds

    def __lt__(self, other):
        if not isinstance(other, Duration):
            return NotImplemented
        return self._nanoseconds < other._nanoseconds

    def __le__(self, other):
        if not isinstance(other, Duration):
            return NotImplemented
        return self._nanoseconds <= other._nanoseconds

    def __gt__(self, other):
        if not isinstance(other, Duration):
            return NotImplemented
        return self._nanoseconds > other._nanoseconds

    def __ge__(self, other):
        if not isinstance(other, Duration):
            return NotImplemented
        return self._nanoseconds >= other._nanoseconds

    def __add__(self, other):
        if isinstance(other, Duration):
            return Duration(nanoseconds=self._nanoseconds + other._nanoseconds)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Duration):
            return Duration(nanoseconds=self._nanoseconds - other._nanoseconds)
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Duration(nanoseconds=int(self._nanoseconds * other))
        return NotImplemented

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return Duration(nanoseconds=int(self._nanoseconds / other))
        if isinstance(other, Duration):
            return self._nanoseconds / other._nanoseconds
        return NotImplemented

    def __repr__(self):
        return f"Duration(nanoseconds={self._nanoseconds})"

    def __hash__(self):
        return hash(self._nanoseconds)
