# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Environment variable substitution."""

from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class EnvironmentVariable(Substitution):
    """Substitution that returns an environment variable value."""

    def __init__(
        self,
        name: str,
        *,
        default_value: Optional['SomeSubstitutionsType'] = None,
    ):
        """
        Create an EnvironmentVariable substitution.

        :param name: The name of the environment variable.
        :param default_value: Optional default value if not set.
        """
        super().__init__()
        self._name = name
        self._default_value = default_value

    @property
    def name(self) -> str:
        """Get the environment variable name."""
        return self._name

    @property
    def default_value(self) -> Optional['SomeSubstitutionsType']:
        """Get the default value."""
        return self._default_value

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"EnvironmentVariable('{self._name}')"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        # Check context environment first
        if self._name in context.environment:
            return context.environment[self._name]
        
        # Then check actual environment
        if self._name in os.environ:
            return os.environ[self._name]
        
        # Use default if provided
        if self._default_value is not None:
            return context.perform_substitution(self._default_value)
        
        raise KeyError(
            f"Environment variable '{self._name}' not found and no default provided"
        )
