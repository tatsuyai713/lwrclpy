from __future__ import annotations

from enum import Enum
from typing import Any


class TopicEndpointTypeEnum(Enum):
    INVALID = 0
    PUBLISHER = 1
    SUBSCRIPTION = 2


class TopicEndpointInfo:
    """rclpy-compatible topic endpoint metadata container."""

    def __init__(
        self,
        *,
        node_name: str = "",
        node_namespace: str = "",
        topic_type: str = "",
        endpoint_type: TopicEndpointTypeEnum = TopicEndpointTypeEnum.INVALID,
        endpoint_gid=None,
        qos_profile: Any = None,
    ):
        self.node_name = node_name
        self.node_namespace = node_namespace
        self.topic_type = topic_type
        self.endpoint_type = endpoint_type
        self.endpoint_gid = list(endpoint_gid) if endpoint_gid is not None else [0] * 16
        self.qos_profile = qos_profile

    def __repr__(self) -> str:
        return (
            "TopicEndpointInfo("
            f"node_name={self.node_name!r}, "
            f"node_namespace={self.node_namespace!r}, "
            f"topic_type={self.topic_type!r}, "
            f"endpoint_type={self.endpoint_type!r}, "
            f"endpoint_gid={self.endpoint_gid!r}, "
            f"qos_profile={self.qos_profile!r})"
        )
