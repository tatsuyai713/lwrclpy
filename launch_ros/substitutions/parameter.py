# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Parameter substitution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from launch.substitutions.substitution import Substitution

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.some_substitutions_type import SomeSubstitutionsType


class Parameter(Substitution):
    """Substitution that returns a parameter value."""

    def __init__(
        self,
        name: 'SomeSubstitutionsType',
    ):
        """
        Create a Parameter substitution.

        :param name: The parameter name.
        """
        super().__init__()
        self._name = name

    @property
    def name(self) -> 'SomeSubstitutionsType':
        """Get the parameter name."""
        return self._name

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"Parameter({self._name})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        param_name = context.perform_substitution(self._name)
        
        if hasattr(context, '_ros_parameters') and param_name in context._ros_parameters:
            return str(context._ros_parameters[param_name])
        
        raise KeyError(f"Parameter '{param_name}' not found")
