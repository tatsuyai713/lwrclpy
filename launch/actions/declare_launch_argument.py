# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Declare a launch argument that can be passed from command line."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class DeclareLaunchArgument(Action):
    """
    Action that declares a launch argument.
    
    Arguments can be passed from the command line using:
        ros2 launch <package> <launch_file> arg_name:=value
    """

    def __init__(
        self,
        name: str,
        *,
        default_value: Optional['SomeSubstitutionsType'] = None,
        description: str = 'no description given',
        choices: Optional[Sequence[str]] = None,
        **kwargs,
    ):
        """
        Create a DeclareLaunchArgument action.

        :param name: The name of the argument.
        :param default_value: Default value if not provided.
        :param description: Description of the argument.
        :param choices: Optional list of valid choices.
        """
        super().__init__(**kwargs)
        self._name = name
        self._default_value = default_value
        self._description = description
        self._choices = choices if choices is not None else []

    @property
    def name(self) -> str:
        """Get the argument name."""
        return self._name

    @property
    def default_value(self) -> Optional['SomeSubstitutionsType']:
        """Get the default value."""
        return self._default_value

    @property
    def description(self) -> str:
        """Get the description."""
        return self._description

    @property
    def choices(self) -> Sequence[str]:
        """Get valid choices."""
        return self._choices

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute the action to declare the argument."""
        # Check if value was already provided (e.g., from command line)
        if self._name not in context.launch_configurations:
            if self._default_value is not None:
                # Perform substitution if needed
                value = context.perform_substitution(self._default_value)
                context.launch_configurations[self._name] = value
            else:
                # No default value and not provided - this is an error
                raise RuntimeError(
                    f"Required launch argument '{self._name}' was not provided. "
                    f"Description: {self._description}"
                )
        else:
            # Validate against choices if provided
            value = context.launch_configurations[self._name]
            if self._choices and value not in self._choices:
                raise RuntimeError(
                    f"Launch argument '{self._name}' has invalid value '{value}'. "
                    f"Valid choices are: {self._choices}"
                )

        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"DeclareLaunchArgument(name='{self._name}', description='{self._description}')"
