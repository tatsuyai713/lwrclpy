# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Launch configuration not equals condition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .condition import Condition

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class LaunchConfigurationNotEquals(Condition):
    """Condition that checks if a launch configuration does not equal a value."""

    def __init__(
        self,
        launch_configuration_name: str,
        expected_value: 'SomeSubstitutionsType',
    ):
        """
        Create a LaunchConfigurationNotEquals condition.

        :param launch_configuration_name: The name of the launch configuration.
        :param expected_value: The value to compare against.
        """
        super().__init__()
        self._launch_configuration_name = launch_configuration_name
        self._expected_value = expected_value

    def describe(self) -> str:
        """Return a description of this condition."""
        return f"LaunchConfigurationNotEquals('{self._launch_configuration_name}' != {self._expected_value})"

    def evaluate(self, context: 'LaunchContext') -> bool:
        """Evaluate the condition."""
        actual = context.launch_configurations.get(self._launch_configuration_name, '')
        expected = context.perform_substitution(self._expected_value)
        return actual != expected
