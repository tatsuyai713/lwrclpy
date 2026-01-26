# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Group actions together."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity


class GroupAction(Action):
    """Action that groups other actions together."""

    def __init__(
        self,
        actions: Iterable['LaunchDescriptionEntity'],
        *,
        scoped: bool = True,
        forwarding: bool = True,
        launch_configurations: Optional[dict] = None,
        **kwargs,
    ):
        """
        Create a GroupAction.

        :param actions: The actions to group.
        :param scoped: If True, create a new scope for configurations.
        :param forwarding: If True, forward configurations from parent scope.
        :param launch_configurations: Additional launch configurations for this group.
        """
        super().__init__(**kwargs)
        self._actions = list(actions)
        self._scoped = scoped
        self._forwarding = forwarding
        self._launch_configurations = launch_configurations or {}

    @property
    def actions(self) -> List['LaunchDescriptionEntity']:
        """Get the grouped actions."""
        return self._actions

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute the grouped actions."""
        if self._scoped:
            # Push new configuration scope
            context._push_configuration_scope(self._forwarding)
            
            # Apply group-specific configurations
            for key, value in self._launch_configurations.items():
                resolved = context.perform_substitution(value)
                context.launch_configurations[key] = resolved

        # Return actions to be executed
        return self._actions

    def describe_sub_entities(self) -> List['LaunchDescriptionEntity']:
        """Return the grouped actions."""
        return list(self._actions)
