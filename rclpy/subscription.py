from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from lwrclpy.subscription import MessageInfo, Subscription


@dataclass
class ContentFilterOptions:
    filter_expression: str
    expression_parameters: Iterable[str] = field(default_factory=tuple)


__all__ = ["ContentFilterOptions", "MessageInfo", "Subscription"]
