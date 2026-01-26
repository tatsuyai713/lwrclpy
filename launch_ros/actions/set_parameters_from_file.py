# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Set parameters from file action."""

from __future__ import annotations

import os
from typing import List, Optional, TYPE_CHECKING

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from launch.actions import Action

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.launch_description import LaunchDescriptionEntity
    from launch.some_substitutions_type import SomeSubstitutionsType


class SetParametersFromFile(Action):
    """Action to set ROS parameters from a YAML file."""

    def __init__(
        self,
        filename: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a SetParametersFromFile action.

        :param filename: Path to the YAML parameter file.
        """
        super().__init__(**kwargs)
        self._filename = filename

    @property
    def filename(self) -> 'SomeSubstitutionsType':
        """Get the filename."""
        return self._filename

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Load parameters from file."""
        filename = context.perform_substitution(self._filename)
        
        if not os.path.isfile(filename):
            raise FileNotFoundError(f"Parameter file not found: {filename}")
        
        # Store in context for nodes to use
        if not hasattr(context, '_ros_parameter_files'):
            context._ros_parameter_files = []
        
        context._ros_parameter_files.append(filename)
        
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"SetParametersFromFile({self._filename})"
