# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Set launch configuration action."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class SetLaunchConfiguration(Action):
    """Action that sets a launch configuration."""

    def __init__(
        self,
        name: str,
        value: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a SetLaunchConfiguration action.

        :param name: The configuration name.
        :param value: The value to set.
        """
        super().__init__(**kwargs)
        self._name = name
        self._value = value

    @property
    def name(self) -> str:
        """Get the configuration name."""
        return self._name

    @property
    def value(self) -> 'SomeSubstitutionsType':
        """Get the value."""
        return self._value

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Set the launch configuration."""
        value_str = context.perform_substitution(self._value)
        context.launch_configurations[self._name] = value_str
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"SetLaunchConfiguration(name={self._name}, value={self._value})"
