from enum import Enum
from typing import Optional

try:
    import fastdds  # Fast DDS v3 の Python API を想定
except Exception as e:
    raise RuntimeError("fastdds Python bindings are not available") from e


# Python API では、QoS の kind はモジュール直下の定数で提供される
# 参考（v3系のPython API）:
#  - History:  fastdds.KEEP_LAST_HISTORY_QOS / fastdds.KEEP_ALL_HISTORY_QOS
#  - Reliability: fastdds.RELIABLE_RELIABILITY_QOS / fastdds.BEST_EFFORT_RELIABILITY_QOS
#  - Durability:  fastdds.VOLATILE_DURABILITY_QOS / fastdds.TRANSIENT_LOCAL_DURABILITY_QOS

# 存在チェック（ない場合は v3 API 未満／不整合）
REQUIRED = [
    "KEEP_LAST_HISTORY_QOS", "KEEP_ALL_HISTORY_QOS",
    "RELIABLE_RELIABILITY_QOS", "BEST_EFFORT_RELIABILITY_QOS",
    "VOLATILE_DURABILITY_QOS", "TRANSIENT_LOCAL_DURABILITY_QOS",
]
_missing = [n for n in REQUIRED if not hasattr(fastdds, n)]
if _missing:
    raise AttributeError(
        "Fast DDS Python API does not expose expected v3 symbols: "
        + ", ".join(_missing)
        + ". Reinstall Fast-DDS v3 + Fast-DDS-python (colcon) to match v3 Python API."
    )


class HistoryPolicy(Enum):
    KEEP_LAST = fastdds.KEEP_LAST_HISTORY_QOS
    KEEP_ALL = fastdds.KEEP_ALL_HISTORY_QOS
    SYSTEM_DEFAULT = fastdds.KEEP_LAST_HISTORY_QOS  # fallback
    UNKNOWN = fastdds.KEEP_LAST_HISTORY_QOS  # fallback


class ReliabilityPolicy(Enum):
    RELIABLE = fastdds.RELIABLE_RELIABILITY_QOS
    BEST_EFFORT = fastdds.BEST_EFFORT_RELIABILITY_QOS
    SYSTEM_DEFAULT = fastdds.RELIABLE_RELIABILITY_QOS  # fallback
    UNKNOWN = fastdds.RELIABLE_RELIABILITY_QOS  # fallback


class DurabilityPolicy(Enum):
    VOLATILE = fastdds.VOLATILE_DURABILITY_QOS
    TRANSIENT_LOCAL = fastdds.TRANSIENT_LOCAL_DURABILITY_QOS
    SYSTEM_DEFAULT = fastdds.VOLATILE_DURABILITY_QOS  # fallback
    UNKNOWN = fastdds.VOLATILE_DURABILITY_QOS  # fallback


class LivelinessPolicy(Enum):
    """Liveliness policy for detecting dead nodes."""
    AUTOMATIC = 0
    MANUAL_BY_PARTICIPANT = 1
    MANUAL_BY_TOPIC = 2
    SYSTEM_DEFAULT = 0
    UNKNOWN = 0


# Infinite duration constant for QoS settings
class _InfiniteDuration:
    """Represents an infinite duration for QoS settings."""
    @property
    def nanoseconds(self) -> int:
        return 0x7FFFFFFFFFFFFFFF  # Max int64
    
    def __repr__(self):
        return "INFINITE_DURATION"


INFINITE_DURATION = _InfiniteDuration()


class Duration:
    """Duration value for QoS settings."""
    __slots__ = ("_nanoseconds",)
    
    def __init__(self, *, seconds: float = 0.0, nanoseconds: int = 0):
        total_ns = int(nanoseconds)
        total_ns += int(seconds * 1_000_000_000)
        self._nanoseconds = total_ns
    
    @property
    def nanoseconds(self) -> int:
        return self._nanoseconds
    
    def __repr__(self):
        return f"Duration(nanoseconds={self._nanoseconds})"


class QoSProfile:
    """
    rclpy 風の QoSProfile（完全版）。
    Fast DDS v3 の DataWriterQos / DataReaderQos に適用。
    Supports: history, depth, reliability, durability, lifespan, deadline, liveliness.
    """
    def __init__(
        self,
        depth: int = 10,
        history: HistoryPolicy = HistoryPolicy.KEEP_LAST,
        reliability: ReliabilityPolicy = ReliabilityPolicy.RELIABLE,
        durability: DurabilityPolicy = DurabilityPolicy.VOLATILE,
        lifespan: Optional[Duration] = None,
        deadline: Optional[Duration] = None,
        liveliness: LivelinessPolicy = LivelinessPolicy.SYSTEM_DEFAULT,
        liveliness_lease_duration: Optional[Duration] = None,
        avoid_ros_namespace_conventions: bool = False,
    ):
        self.depth = int(depth)
        self.history = history
        self.reliability = reliability
        self.durability = durability
        self.lifespan = lifespan
        self.deadline = deadline
        self.liveliness = liveliness
        self.liveliness_lease_duration = liveliness_lease_duration
        self.avoid_ros_namespace_conventions = avoid_ros_namespace_conventions

    def _apply_duration(self, target, duration_value: Optional[Duration]):
        """Apply duration to a QoS duration field."""
        if duration_value is None:
            return
        try:
            ns = duration_value.nanoseconds
            if hasattr(target, "seconds") and hasattr(target, "nanosec"):
                target.seconds = ns // 1_000_000_000
                target.nanosec = ns % 1_000_000_000
            elif hasattr(target, "sec") and hasattr(target, "nanosec"):
                target.sec = ns // 1_000_000_000
                target.nanosec = ns % 1_000_000_000
        except Exception:
            pass

    def apply_to_writer(self, wq: "fastdds.DataWriterQos"):
        # History
        wq.history().kind = self.history.value
        # KEEP_LAST のときのみ意味を持つが、設定しても害はない
        try:
            wq.history().depth = self.depth
        except Exception:
            pass
        # Reliability / Durability
        wq.reliability().kind = self.reliability.value
        wq.durability().kind = self.durability.value
        
        # Lifespan (writer only)
        if self.lifespan is not None:
            try:
                self._apply_duration(wq.lifespan().duration, self.lifespan)
            except Exception:
                pass
        
        # Deadline
        if self.deadline is not None:
            try:
                self._apply_duration(wq.deadline().period, self.deadline)
            except Exception:
                pass
        
        # Liveliness
        try:
            liveliness_kinds = {
                LivelinessPolicy.AUTOMATIC: getattr(fastdds, "AUTOMATIC_LIVELINESS_QOS", 0),
                LivelinessPolicy.MANUAL_BY_PARTICIPANT: getattr(fastdds, "MANUAL_BY_PARTICIPANT_LIVELINESS_QOS", 1),
                LivelinessPolicy.MANUAL_BY_TOPIC: getattr(fastdds, "MANUAL_BY_TOPIC_LIVELINESS_QOS", 2),
            }
            wq.liveliness().kind = liveliness_kinds.get(self.liveliness, 0)
            if self.liveliness_lease_duration is not None:
                self._apply_duration(wq.liveliness().lease_duration, self.liveliness_lease_duration)
        except Exception:
            pass

    def apply_to_reader(self, rq: "fastdds.DataReaderQos"):
        rq.history().kind = self.history.value
        try:
            rq.history().depth = self.depth
        except Exception:
            pass
        rq.reliability().kind = self.reliability.value
        rq.durability().kind = self.durability.value
        
        # Deadline
        if self.deadline is not None:
            try:
                self._apply_duration(rq.deadline().period, self.deadline)
            except Exception:
                pass
        
        # Liveliness
        try:
            liveliness_kinds = {
                LivelinessPolicy.AUTOMATIC: getattr(fastdds, "AUTOMATIC_LIVELINESS_QOS", 0),
                LivelinessPolicy.MANUAL_BY_PARTICIPANT: getattr(fastdds, "MANUAL_BY_PARTICIPANT_LIVELINESS_QOS", 1),
                LivelinessPolicy.MANUAL_BY_TOPIC: getattr(fastdds, "MANUAL_BY_TOPIC_LIVELINESS_QOS", 2),
            }
            rq.liveliness().kind = liveliness_kinds.get(self.liveliness, 0)
            if self.liveliness_lease_duration is not None:
                self._apply_duration(rq.liveliness().lease_duration, self.liveliness_lease_duration)
        except Exception:
            pass

    # ---- Convenience constructors (rclpy-like) --------------------
    @classmethod
    def keep_last(cls, depth: int) -> "QoSProfile":
        return cls(depth=depth, history=HistoryPolicy.KEEP_LAST)

    @classmethod
    def keep_all(cls) -> "QoSProfile":
        return cls(depth=0, history=HistoryPolicy.KEEP_ALL)

    @classmethod
    def sensor_data(cls) -> "QoSProfile":
        # Mirrors ROS2 SensorData QoS (best-effort, volatile, depth=5)
        return cls(
            depth=5,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

    @classmethod
    def system_default(cls) -> "QoSProfile":
        return cls()

    @classmethod
    def parameters(cls) -> "QoSProfile":
        # ROS2 parameters usually use reliable/volatile keep last depth 1000
        return cls(depth=1000)

    @classmethod
    def services_default(cls) -> "QoSProfile":
        # Services default to reliable/volatile keep last depth 10
        return cls(depth=10)

    @classmethod
    def parameter_events(cls) -> "QoSProfile":
        """QoS for parameter events (reliable, transient local)."""
        return cls(
            depth=1000,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

    @classmethod
    def action_status_default(cls) -> "QoSProfile":
        """QoS for action status topics."""
        return cls(
            depth=1,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

    @classmethod
    def best_available(cls) -> "QoSProfile":
        """Best available QoS that adapts to publisher's QoS."""
        return cls(
            depth=10,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )


# Predefined QoS profiles matching rclpy
qos_profile_sensor_data = QoSProfile.sensor_data()
qos_profile_system_default = QoSProfile.system_default()
qos_profile_services_default = QoSProfile.services_default()
qos_profile_parameters = QoSProfile.parameters()
qos_profile_parameter_events = QoSProfile.parameter_events()
qos_profile_action_status_default = QoSProfile.action_status_default()
qos_profile_best_available = QoSProfile.best_available()
