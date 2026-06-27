from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Iterable, Optional


class QoSPolicyKind(Enum):
    INVALID = auto()
    DURABILITY = auto()
    DEADLINE = auto()
    LIFESPAN = auto()
    LIVELINESS = auto()
    LIVELINESS_LEASE_DURATION = auto()
    RELIABILITY = auto()
    HISTORY = auto()
    DEPTH = auto()
    AVOID_ROS_NAMESPACE_CONVENTIONS = auto()


@dataclass
class QoSOverridingOptions:
    policy_kinds: Iterable[QoSPolicyKind] = field(default_factory=tuple)
    callback: Optional[Callable] = None
    id: Optional[str] = None

    @classmethod
    def with_default_policies(cls, *, callback=None, id=None):
        return cls(
            policy_kinds=(
                QoSPolicyKind.HISTORY,
                QoSPolicyKind.DEPTH,
                QoSPolicyKind.RELIABILITY,
                QoSPolicyKind.DURABILITY,
            ),
            callback=callback,
            id=id,
        )


__all__ = ["QoSPolicyKind", "QoSOverridingOptions"]
