# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Timer action - execute actions after a delay."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Iterable, List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class TimerAction(Action):
    """Action that executes sub-actions after a delay."""

    def __init__(
        self,
        *,
        period: 'SomeSubstitutionsType',
        actions: Iterable['LaunchDescriptionEntity'],
        cancel_on_shutdown: bool = True,
        **kwargs,
    ):
        """
        Create a TimerAction.

        :param period: The delay period in seconds.
        :param actions: The actions to execute after the delay.
        :param cancel_on_shutdown: Whether to cancel if shutdown is requested.
        """
        super().__init__(**kwargs)
        self._period = period
        self._actions = list(actions)
        self._cancel_on_shutdown = cancel_on_shutdown
        self._timer: Optional[threading.Timer] = None

    @property
    def period(self) -> 'SomeSubstitutionsType':
        """Get the delay period."""
        return self._period

    @property
    def actions(self) -> List['LaunchDescriptionEntity']:
        """Get the actions."""
        return self._actions

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Start the timer."""
        period_str = context.perform_substitution(self._period)
        period = float(period_str)

        def timer_callback():
            # Execute actions when timer fires
            # Note: In a full implementation, this would properly integrate
            # with the launch service's execution loop
            for action in self._actions:
                if hasattr(action, 'execute'):
                    action.execute(context)

        # Start timer in a thread
        self._timer = threading.Timer(period, timer_callback)
        self._timer.daemon = True
        self._timer.start()

        return None

    def cancel(self) -> None:
        """Cancel the timer."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"TimerAction(period={self._period}, actions={len(self._actions)})"

    def describe_sub_entities(self) -> List['LaunchDescriptionEntity']:
        """Return the sub-actions."""
        return list(self._actions)
