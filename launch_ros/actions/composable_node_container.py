# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Composable node container action (stub for API compatibility)."""

from __future__ import annotations

from typing import List, Optional, Sequence, TYPE_CHECKING

from .node import Node

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.launch_description import LaunchDescriptionEntity
    from launch.some_substitutions_type import SomeSubstitutionsType


class ComposableNode:
    """Description of a composable node."""

    def __init__(
        self,
        *,
        package: 'SomeSubstitutionsType',
        plugin: 'SomeSubstitutionsType',
        name: Optional['SomeSubstitutionsType'] = None,
        namespace: Optional['SomeSubstitutionsType'] = None,
        parameters: Optional[Sequence] = None,
        remappings: Optional[Sequence] = None,
        extra_arguments: Optional[Sequence] = None,
    ):
        """
        Create a ComposableNode description.

        Note: lwrclpy does not support component containers, this is for API compatibility.
        """
        self.package = package
        self.plugin = plugin
        self.name = name
        self.namespace = namespace
        self.parameters = parameters or []
        self.remappings = remappings or []
        self.extra_arguments = extra_arguments or []


class ComposableNodeContainer(Node):
    """Container for composable nodes (stub for API compatibility)."""

    def __init__(
        self,
        *,
        composable_node_descriptions: Optional[Sequence[ComposableNode]] = None,
        **kwargs,
    ):
        """
        Create a ComposableNodeContainer action.

        Note: lwrclpy does not support component containers.
        This is provided for API compatibility but will not load components.
        """
        super().__init__(**kwargs)
        self._composable_node_descriptions = composable_node_descriptions or []

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute (warn about lack of support)."""
        import sys
        print(
            "[WARN] ComposableNodeContainer is not supported in lwrclpy. "
            "Components will not be loaded.",
            file=sys.stderr
        )
        return super()._execute_impl(context)

    def describe(self) -> str:
        """Return a description of this action."""
        return f"ComposableNodeContainer(nodes={len(self._composable_node_descriptions)})"
