# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Load composable nodes action (stub for API compatibility)."""

from __future__ import annotations

import sys
from typing import List, Optional, Sequence, TYPE_CHECKING

from launch.actions import Action

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.launch_description import LaunchDescriptionEntity
    from launch.some_substitutions_type import SomeSubstitutionsType
    from .composable_node_container import ComposableNode


class LoadComposableNodes(Action):
    """Action to load composable nodes (stub for API compatibility)."""

    def __init__(
        self,
        *,
        composable_node_descriptions: Sequence['ComposableNode'],
        target_container: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a LoadComposableNodes action.

        Note: lwrclpy does not support component containers.
        This is provided for API compatibility only.
        """
        super().__init__(**kwargs)
        self._composable_node_descriptions = composable_node_descriptions
        self._target_container = target_container

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute (warn about lack of support)."""
        print(
            "[WARN] LoadComposableNodes is not supported in lwrclpy. "
            "Components will not be loaded.",
            file=sys.stderr
        )
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"LoadComposableNodes(nodes={len(self._composable_node_descriptions)})"
