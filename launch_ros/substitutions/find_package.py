# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Find package substitutions."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from launch.substitutions.substitution import Substitution

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.some_substitutions_type import SomeSubstitutionsType


class FindPackagePrefix(Substitution):
    """Substitution that finds a ROS 2 package prefix directory."""

    def __init__(
        self,
        package: 'SomeSubstitutionsType',
    ):
        """
        Create a FindPackagePrefix substitution.

        Note: Since lwrclpy doesn't use ament, this will check common locations.

        :param package: The package name.
        """
        super().__init__()
        self._package = package

    @property
    def package(self) -> 'SomeSubstitutionsType':
        """Get the package name."""
        return self._package

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"FindPackagePrefix({self._package})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        package_name = context.perform_substitution(self._package)
        
        # Check if it's in PYTHONPATH or common locations
        possible_paths = [
            os.path.join(os.getcwd(), package_name),
            os.path.join(os.getcwd(), 'examples', package_name),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), package_name),
        ]
        
        # Check AMENT_PREFIX_PATH if available
        ament_prefix = os.environ.get('AMENT_PREFIX_PATH', '')
        for prefix in ament_prefix.split(':'):
            if prefix:
                possible_paths.append(prefix)
        
        for path in possible_paths:
            if os.path.isdir(path):
                return path
        
        # Return current directory as fallback
        return os.getcwd()


class FindPackageShare(Substitution):
    """Substitution that finds a ROS 2 package share directory."""

    def __init__(
        self,
        package: 'SomeSubstitutionsType',
    ):
        """
        Create a FindPackageShare substitution.

        Note: Since lwrclpy doesn't use ament, this will check common locations.

        :param package: The package name.
        """
        super().__init__()
        self._package = package

    @property
    def package(self) -> 'SomeSubstitutionsType':
        """Get the package name."""
        return self._package

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"FindPackageShare({self._package})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        package_name = context.perform_substitution(self._package)
        
        # Check common share locations
        possible_paths = [
            os.path.join(os.getcwd(), package_name),
            os.path.join(os.getcwd(), 'share', package_name),
            os.path.join(os.getcwd(), 'examples', package_name),
        ]
        
        # Check AMENT_PREFIX_PATH if available
        ament_prefix = os.environ.get('AMENT_PREFIX_PATH', '')
        for prefix in ament_prefix.split(':'):
            if prefix:
                possible_paths.append(os.path.join(prefix, 'share', package_name))
        
        for path in possible_paths:
            if os.path.isdir(path):
                return path
        
        # Return current directory as fallback
        return os.getcwd()
