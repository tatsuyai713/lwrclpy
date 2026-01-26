# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Launch configuration substitution."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class LaunchConfiguration(Substitution):
    """Substitution that returns a launch configuration value."""

    def __init__(
        self,
        variable_name: str,
        *,
        default: Optional['SomeSubstitutionsType'] = None,
    ):
        """
        Create a LaunchConfiguration substitution.

        :param variable_name: The name of the launch configuration.
        :param default: Optional default value if not set.
        """
        super().__init__()
        self._variable_name = variable_name
        self._default = default

    @property
    def variable_name(self) -> str:
        """Get the variable name."""
        return self._variable_name

    @property
    def default(self) -> Optional['SomeSubstitutionsType']:
        """Get the default value."""
        return self._default

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"LaunchConfiguration('{self._variable_name}')"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        if self._variable_name in context.launch_configurations:
            return context.launch_configurations[self._variable_name]
        elif self._default is not None:
            return context.perform_substitution(self._default)
        else:
            raise KeyError(
                f"Launch configuration '{self._variable_name}' not found and no default provided"
            )
