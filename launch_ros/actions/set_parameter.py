# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Set parameter action."""

from __future__ import annotations

from typing import Any, List, Optional, TYPE_CHECKING

from launch.actions import Action

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.launch_description import LaunchDescriptionEntity
    from launch.some_substitutions_type import SomeSubstitutionsType


class SetParameter(Action):
    """Action to set a ROS parameter."""

    def __init__(
        self,
        name: 'SomeSubstitutionsType',
        value: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a SetParameter action.

        :param name: The parameter name.
        :param value: The parameter value.
        """
        super().__init__(**kwargs)
        self._name = name
        self._value = value

    @property
    def name(self) -> 'SomeSubstitutionsType':
        """Get the parameter name."""
        return self._name

    @property
    def value(self) -> 'SomeSubstitutionsType':
        """Get the parameter value."""
        return self._value

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Set the parameter."""
        name_str = context.perform_substitution(self._name)
        value_str = context.perform_substitution(self._value)
        
        # Store in context for nodes to use
        if not hasattr(context, '_ros_parameters'):
            context._ros_parameters = {}
        
        context._ros_parameters[name_str] = value_str
        
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"SetParameter(name={self._name}, value={self._value})"
