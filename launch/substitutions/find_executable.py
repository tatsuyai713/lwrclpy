# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Find executable substitution."""

from __future__ import annotations

import os
import shutil
from typing import Optional, TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class FindExecutable(Substitution):
    """Substitution that finds an executable in PATH."""

    def __init__(
        self,
        *,
        name: 'SomeSubstitutionsType',
    ):
        """
        Create a FindExecutable substitution.

        :param name: The name of the executable to find.
        """
        super().__init__()
        self._name = name

    @property
    def name(self) -> 'SomeSubstitutionsType':
        """Get the executable name."""
        return self._name

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"FindExecutable(name={self._name})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution by finding the executable."""
        name = context.perform_substitution(self._name)
        
        # Use shutil.which to find the executable
        path = shutil.which(name)
        if path is None:
            raise RuntimeError(f"Executable '{name}' not found in PATH")
        
        return path
