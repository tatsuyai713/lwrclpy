from lwrclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
    HistoryPolicy,
    LivelinessPolicy,
    qos_profile_sensor_data,
    qos_profile_system_default,
    qos_profile_services_default,
    qos_profile_parameters,
    qos_profile_parameter_events,
    qos_profile_best_available,
    qos_profile_low_latency,
    qos_profile_high_throughput,
    qos_profile_bulk_reliable,
    INFINITE_DURATION,
    Duration,
)

# rclpy-style aliases
QoSReliabilityPolicy = ReliabilityPolicy
QoSDurabilityPolicy = DurabilityPolicy
QoSHistoryPolicy = HistoryPolicy
QoSLivelinessPolicy = LivelinessPolicy


# Predefined profiles as module-level constants
class QoSPresetProfiles:
    """Collection of commonly used QoS presets."""
    SENSOR_DATA = qos_profile_sensor_data
    SYSTEM_DEFAULT = qos_profile_system_default
    SERVICES_DEFAULT = qos_profile_services_default
    PARAMETERS = qos_profile_parameters
    PARAMETER_EVENTS = qos_profile_parameter_events
    ACTION_STATUS_DEFAULT = QoSProfile.action_status_default()
    LOW_LATENCY = qos_profile_low_latency
    HIGH_THROUGHPUT = qos_profile_high_throughput
    BULK_RELIABLE = qos_profile_bulk_reliable


__all__ = [
    "QoSProfile",
    "QoSReliabilityPolicy",
    "QoSDurabilityPolicy",
    "QoSHistoryPolicy",
    "QoSLivelinessPolicy",
    "ReliabilityPolicy",
    "DurabilityPolicy",
    "HistoryPolicy",
    "LivelinessPolicy",
    "QoSPresetProfiles",
    "qos_profile_sensor_data",
    "qos_profile_system_default",
    "qos_profile_services_default",
    "qos_profile_parameters",
    "qos_profile_parameter_events",
    "qos_profile_best_available",
    "qos_profile_low_latency",
    "qos_profile_high_throughput",
    "qos_profile_bulk_reliable",
    "INFINITE_DURATION",
    "Duration",
]
