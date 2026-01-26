# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Push ROS namespace action."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from launch.actions import Action

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.launch_description import LaunchDescriptionEntity
    from launch.some_substitutions_type import SomeSubstitutionsType


class PushROSNamespace(Action):
    """Action to push a ROS namespace onto the stack."""

    def __init__(
        self,
        namespace: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a PushROSNamespace action.

        :param namespace: The namespace to push.
        """
        super().__init__(**kwargs)
        self._namespace = namespace

    @property
    def namespace(self) -> 'SomeSubstitutionsType':
        """Get the namespace."""
        return self._namespace

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Push the namespace."""
        namespace = context.perform_substitution(self._namespace)
        
        # Get current namespace stack
        if not hasattr(context, '_ros_namespace_stack'):
            context._ros_namespace_stack = []
        
        context._ros_namespace_stack.append(namespace)
        
        # Update the current namespace in configurations
        full_namespace = '/'.join(context._ros_namespace_stack)
        if full_namespace and not full_namespace.startswith('/'):
            full_namespace = '/' + full_namespace
        context.launch_configurations['ros_namespace'] = full_namespace
        
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"PushROSNamespace({self._namespace})"


class PopROSNamespace(Action):
    """Action to pop a ROS namespace from the stack."""

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Pop the namespace."""
        if hasattr(context, '_ros_namespace_stack') and context._ros_namespace_stack:
            context._ros_namespace_stack.pop()
            
            # Update the current namespace in configurations
            full_namespace = '/'.join(context._ros_namespace_stack)
            if full_namespace and not full_namespace.startswith('/'):
                full_namespace = '/' + full_namespace
            context.launch_configurations['ros_namespace'] = full_namespace
        
        return None
