# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Push and pop launch configurations scope."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity


class PushLaunchConfigurations(Action):
    """Action that pushes a new configuration scope."""

    def __init__(
        self,
        *,
        forwarding: bool = True,
        **kwargs,
    ):
        """
        Create a PushLaunchConfigurations action.

        :param forwarding: If True, copy current configurations to new scope.
        """
        super().__init__(**kwargs)
        self._forwarding = forwarding

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Push a new configuration scope."""
        context._push_configuration_scope(self._forwarding)
        return None


class PopLaunchConfigurations(Action):
    """Action that pops the current configuration scope."""

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Pop the current configuration scope."""
        context._pop_configuration_scope()
        return None
