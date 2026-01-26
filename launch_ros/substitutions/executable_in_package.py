# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Executable in package substitution."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from launch.substitutions.substitution import Substitution

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.some_substitutions_type import SomeSubstitutionsType


class ExecutableInPackage(Substitution):
    """Substitution that finds an executable in a package."""

    def __init__(
        self,
        executable: 'SomeSubstitutionsType',
        package: 'SomeSubstitutionsType',
    ):
        """
        Create an ExecutableInPackage substitution.

        :param executable: The executable name.
        :param package: The package name.
        """
        super().__init__()
        self._executable = executable
        self._package = package

    @property
    def executable(self) -> 'SomeSubstitutionsType':
        """Get the executable name."""
        return self._executable

    @property
    def package(self) -> 'SomeSubstitutionsType':
        """Get the package name."""
        return self._package

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"ExecutableInPackage({self._executable}, {self._package})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        executable = context.perform_substitution(self._executable)
        package = context.perform_substitution(self._package)
        
        # Check common locations
        possible_paths = [
            os.path.join(os.getcwd(), package, executable),
            os.path.join(os.getcwd(), 'examples', package, executable),
            os.path.join(os.getcwd(), executable),
        ]
        
        for path in possible_paths:
            if os.path.isfile(path):
                return path
        
        # Try PATH
        which_result = shutil.which(executable)
        if which_result:
            return which_result
        
        # Return executable name as-is
        return executable
