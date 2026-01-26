# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Include another launch description."""

from __future__ import annotations

import os
from typing import Any, Iterable, List, Optional, Tuple, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescription, LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class LaunchDescriptionSource:
    """Base class for launch description sources."""

    def __init__(
        self,
        location: Optional['SomeSubstitutionsType'] = None,
    ):
        """
        Create a LaunchDescriptionSource.

        :param location: The location of the launch description.
        """
        self._location = location

    @property
    def location(self) -> Optional['SomeSubstitutionsType']:
        """Get the location."""
        return self._location

    def get_launch_description(self, context: 'LaunchContext') -> 'LaunchDescription':
        """Get the launch description from this source."""
        raise NotImplementedError("Subclasses must implement get_launch_description()")


class PythonLaunchDescriptionSource(LaunchDescriptionSource):
    """Launch description source for Python launch files."""

    def __init__(
        self,
        launch_file_path: 'SomeSubstitutionsType',
    ):
        """
        Create a PythonLaunchDescriptionSource.

        :param launch_file_path: Path to the Python launch file.
        """
        super().__init__(launch_file_path)
        self._launch_file_path = launch_file_path

    def get_launch_description(self, context: 'LaunchContext') -> 'LaunchDescription':
        """Load and return the launch description from the Python file."""
        from ..launch_description import LaunchDescription

        # Resolve the path
        path = context.perform_substitution(self._launch_file_path)
        
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Launch file not found: {path}")

        # Load the Python file
        import importlib.util
        spec = importlib.util.spec_from_file_location("launch_module", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load launch file: {path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get the launch description
        if not hasattr(module, 'generate_launch_description'):
            raise RuntimeError(
                f"Launch file '{path}' does not have a 'generate_launch_description' function"
            )

        return module.generate_launch_description()


class AnyLaunchDescriptionSource(PythonLaunchDescriptionSource):
    """Launch description source that can handle any format (defaults to Python)."""
    pass


class IncludeLaunchDescription(Action):
    """Action to include another launch description."""

    def __init__(
        self,
        launch_description_source: LaunchDescriptionSource,
        *,
        launch_arguments: Optional[Iterable[Tuple['SomeSubstitutionsType', 'SomeSubstitutionsType']]] = None,
        **kwargs,
    ):
        """
        Create an IncludeLaunchDescription action.

        :param launch_description_source: The source of the launch description.
        :param launch_arguments: Arguments to pass to the included launch.
        """
        super().__init__(**kwargs)
        self._launch_description_source = launch_description_source
        self._launch_arguments = list(launch_arguments) if launch_arguments else []

    @property
    def launch_description_source(self) -> LaunchDescriptionSource:
        """Get the launch description source."""
        return self._launch_description_source

    @property
    def launch_arguments(self) -> List[Tuple['SomeSubstitutionsType', 'SomeSubstitutionsType']]:
        """Get the launch arguments."""
        return self._launch_arguments

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute the include action."""
        # Push a new configuration scope
        context._push_configuration_scope(forwarding=True)

        # Set launch arguments
        for key, value in self._launch_arguments:
            key_str = context.perform_substitution(key)
            value_str = context.perform_substitution(value)
            context.launch_configurations[key_str] = value_str

        # Get and return the launch description entities
        launch_description = self._launch_description_source.get_launch_description(context)
        
        return launch_description.entities

    def describe(self) -> str:
        """Return a description of this action."""
        if self._launch_description_source.location:
            return f"IncludeLaunchDescription({self._launch_description_source.location})"
        return "IncludeLaunchDescription(...)"
