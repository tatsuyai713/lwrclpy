# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Register an event handler."""

from __future__ import annotations

from typing import Any, List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity


class RegisterEventHandler(Action):
    """Action that registers an event handler."""

    def __init__(
        self,
        event_handler: Any,
        **kwargs,
    ):
        """
        Create a RegisterEventHandler action.

        :param event_handler: The event handler to register.
        """
        super().__init__(**kwargs)
        self._event_handler = event_handler

    @property
    def event_handler(self) -> Any:
        """Get the event handler."""
        return self._event_handler

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Register the event handler."""
        context.register_event_handler(self._event_handler)
        return None
