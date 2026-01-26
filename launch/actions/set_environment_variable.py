# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Set environment variable action."""

from __future__ import annotations

import os
from typing import List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class SetEnvironmentVariable(Action):
    """Action that sets an environment variable."""

    def __init__(
        self,
        name: 'SomeSubstitutionsType',
        value: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a SetEnvironmentVariable action.

        :param name: The environment variable name.
        :param value: The value to set.
        """
        super().__init__(**kwargs)
        self._name = name
        self._value = value

    @property
    def name(self) -> 'SomeSubstitutionsType':
        """Get the environment variable name."""
        return self._name

    @property
    def value(self) -> 'SomeSubstitutionsType':
        """Get the value."""
        return self._value

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Set the environment variable."""
        name_str = context.perform_substitution(self._name)
        value_str = context.perform_substitution(self._value)
        
        # Set in context environment
        context.environment[name_str] = value_str
        
        # Also set in actual environment
        os.environ[name_str] = value_str
        
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"SetEnvironmentVariable(name={self._name}, value={self._value})"


class UnsetEnvironmentVariable(Action):
    """Action that unsets an environment variable."""

    def __init__(
        self,
        name: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create an UnsetEnvironmentVariable action.

        :param name: The environment variable name.
        """
        super().__init__(**kwargs)
        self._name = name

    @property
    def name(self) -> 'SomeSubstitutionsType':
        """Get the environment variable name."""
        return self._name

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Unset the environment variable."""
        name_str = context.perform_substitution(self._name)
        
        # Remove from context environment
        context.environment.pop(name_str, None)
        
        # Also remove from actual environment
        os.environ.pop(name_str, None)
        
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"UnsetEnvironmentVariable(name={self._name})"
