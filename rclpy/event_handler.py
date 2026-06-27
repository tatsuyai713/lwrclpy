from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class PublisherEventCallbacks:
    deadline: Optional[Callable] = None
    liveliness: Optional[Callable] = None
    incompatible_qos: Optional[Callable] = None
    matched: Optional[Callable] = None


@dataclass
class SubscriptionEventCallbacks:
    deadline: Optional[Callable] = None
    liveliness: Optional[Callable] = None
    incompatible_qos: Optional[Callable] = None
    message_lost: Optional[Callable] = None
    matched: Optional[Callable] = None


class EventHandler:
    def __init__(self, *, callback=None, callback_group=None, event_type=None, parent_impl=None):
        self.callback = callback
        self.callback_group = callback_group
        self.event_type = event_type
        self.parent_impl = parent_impl

    def is_ready(self, wait_set=None) -> bool:
        return False

    def take_data(self):
        return None

    def execute(self, taken_data=None):
        if self.callback is not None and taken_data is not None:
            return self.callback(taken_data)
        if self.callback is not None:
            return self.callback()
        return None


__all__ = [
    "EventHandler",
    "PublisherEventCallbacks",
    "SubscriptionEventCallbacks",
]
