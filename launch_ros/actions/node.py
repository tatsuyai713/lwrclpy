# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Node action for launching ROS 2 nodes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union, TYPE_CHECKING

from launch.actions import ExecuteProcess

if TYPE_CHECKING:
    from launch.launch_context import LaunchContext
    from launch.launch_description import LaunchDescriptionEntity
    from launch.some_substitutions_type import SomeSubstitutionsType


def _normalize_to_list_of_substitutions(value):
    """Convert value to list for substitution processing."""
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


class Node(ExecuteProcess):
    """
    Action to launch a ROS 2 / lwrclpy node.

    This action provides a convenient way to launch Python nodes without
    needing to specify ExecuteProcess explicitly.

    Examples:
        # Simple usage with just the script path
        Node(executable='examples/pubsub/string/talker.py')

        # With node name and parameters
        Node(
            executable='my_node.py',
            name='my_node',
            parameters=[{'param1': 'value1'}],
        )

        # ROS 2 style (package is optional for lwrclpy)
        Node(
            package='my_package',
            executable='talker',
            name='my_talker',
        )
    """

    def __init__(
        self,
        *,
        executable: Optional['SomeSubstitutionsType'] = None,
        package: Optional['SomeSubstitutionsType'] = None,
        name: Optional['SomeSubstitutionsType'] = None,
        namespace: Optional['SomeSubstitutionsType'] = None,
        exec_name: Optional['SomeSubstitutionsType'] = None,
        parameters: Optional[Sequence[Union[str, Dict, 'SomeSubstitutionsType']]] = None,
        remappings: Optional[Sequence[Tuple['SomeSubstitutionsType', 'SomeSubstitutionsType']]] = None,
        ros_arguments: Optional[Sequence['SomeSubstitutionsType']] = None,
        arguments: Optional[Sequence['SomeSubstitutionsType']] = None,
        node_executable: Optional['SomeSubstitutionsType'] = None,  # Deprecated
        node_name: Optional['SomeSubstitutionsType'] = None,  # Deprecated
        node_namespace: Optional['SomeSubstitutionsType'] = None,  # Deprecated
        output: str = 'screen',
        respawn: bool = False,
        respawn_delay: float = 0.0,
        env: Optional[Dict[str, 'SomeSubstitutionsType']] = None,
        additional_env: Optional[Dict[str, 'SomeSubstitutionsType']] = None,
        **kwargs,
    ):
        """
        Create a Node action.

        :param executable: The executable to run (Python script path or command).
            Can be:
            - Absolute path: '/path/to/script.py'
            - Relative path: 'examples/talker.py'
            - Script name: 'talker.py' (searched in current directory)
        :param package: The ROS 2 package name (optional for lwrclpy, used for compatibility).
        :param name: The node name (sets LWRCLPY_NODE_NAME environment variable).
        :param namespace: The node namespace (sets LWRCLPY_NAMESPACE environment variable).
        :param exec_name: Name for the executable in logs.
        :param parameters: Node parameters (sets LWRCLPY_PARAMS environment variable as JSON).
        :param remappings: Topic/service remappings (sets LWRCLPY_REMAPPINGS environment variable).
        :param ros_arguments: Additional ROS arguments (for ROS 2 compatibility).
        :param arguments: Additional command-line arguments.
        :param output: Output handling ('screen', 'log', 'both').
        :param respawn: Whether to respawn on exit.
        :param respawn_delay: Delay before respawning (seconds).
        :param env: Environment variables to set (replaces current environment).
        :param additional_env: Additional environment variables to set (merged with current).
        """
        # Handle deprecated parameters
        if node_executable is not None and executable is None:
            executable = node_executable
        if node_name is not None and name is None:
            name = node_name
        if node_namespace is not None and namespace is None:
            namespace = node_namespace

        self._package = package
        self._node_executable = executable
        self._node_name = name
        self._node_namespace = namespace
        self._exec_name = exec_name
        self._parameters = parameters or []
        self._remappings = remappings or []
        self._ros_arguments = ros_arguments or []
        self._arguments = arguments or []
        self._node_additional_env = additional_env or {}
        self._node_env = env

        # Build command will be done in execute
        super().__init__(
            cmd=[],  # Will be set in execute
            name=exec_name,
            output=output,
            respawn=respawn,
            respawn_delay=respawn_delay,
            env=env,
            additional_env=additional_env,
            **kwargs,
        )

    @property
    def node_name(self) -> Optional['SomeSubstitutionsType']:
        """Get the node name."""
        return self._node_name

    @property
    def node_namespace(self) -> Optional['SomeSubstitutionsType']:
        """Get the node namespace."""
        return self._node_namespace

    def _resolve_cmd(self, context: 'LaunchContext') -> List[str]:
        """Resolve the command with substitutions.
        
        Override ExecuteProcess._resolve_cmd to build the command
        from package and executable specifications.
        """
        # Since we initialized with cmd=[], we need to build it here
        return self._build_command(context)

    def _resolve_env(self, context: 'LaunchContext') -> Dict[str, str]:
        """Resolve environment variables.
        
        Override ExecuteProcess._resolve_env to add Node-specific
        environment variables.
        """
        # Build the environment with Node-specific variables
        env = self._build_environment(context)
        
        # Also add context environment
        env.update(context.environment)
        
        return env

    def _find_executable(self, executable: str, package: Optional[str], context: 'LaunchContext') -> List[str]:
        """
        Find and return the command to execute the script.
        
        Supports ROS 2 style package/executable specification.
        When package is specified, searches for the executable in:
        - {package}/{executable}
        - {package}/{executable}.py
        - {package}/scripts/{executable}
        - {package}/scripts/{executable}.py
        - src/{package}/{executable}
        - src/{package}/scripts/{executable}
        - install/{package}/lib/{package}/{executable}
        - examples/{package}/{executable}  (lwrclpy specific)
        """
        cmd = []
        search_paths = []

        # Helper to add path with and without .py extension
        def add_path(base_path):
            search_paths.append(base_path)
            if not base_path.endswith('.py'):
                search_paths.append(base_path + '.py')

        cwd = os.getcwd()

        # If package is specified, prioritize package-based paths (ROS 2 style)
        if package:
            # Support both dotted and slash-separated package names
            # e.g., 'pubsub.string' or 'pubsub/string' -> 'pubsub/string'
            pkg_parts = package.replace('.', os.sep)
            
            # Standard ROS 2 workspace layout
            add_path(os.path.join(cwd, 'install', pkg_parts, 'lib', pkg_parts, executable))
            add_path(os.path.join(cwd, 'install', 'lib', pkg_parts, executable))
            
            # Source layout
            add_path(os.path.join(cwd, 'src', pkg_parts, pkg_parts, executable))
            add_path(os.path.join(cwd, 'src', pkg_parts, 'scripts', executable))
            add_path(os.path.join(cwd, 'src', pkg_parts, executable))
            add_path(os.path.join(cwd, pkg_parts, 'scripts', executable))
            add_path(os.path.join(cwd, pkg_parts, executable))
            
            # lwrclpy-specific: examples directory
            add_path(os.path.join(cwd, 'examples', pkg_parts, executable))

        # Direct path (always try)
        add_path(executable)
        add_path(os.path.abspath(executable))
        add_path(os.path.join(cwd, executable))

        # Find the executable
        for path in search_paths:
            if os.path.isfile(path):
                # Check if it's a Python script
                if path.endswith('.py'):
                    cmd = [sys.executable, path]
                else:
                    # Check if it's executable
                    if os.access(path, os.X_OK):
                        cmd = [path]
                    else:
                        cmd = [sys.executable, path]
                break

        # If not found as file, try to find in PATH
        if not cmd:
            which_result = shutil.which(executable)
            if which_result:
                cmd = [which_result]
            else:
                # Last resort: assume it's a Python script
                cmd = [sys.executable, executable]

        return cmd

    def _build_command(self, context: 'LaunchContext') -> List[str]:
        """Build the command to execute."""
        # Resolve executable
        executable = context.perform_substitution(self._node_executable) if self._node_executable else None
        package = context.perform_substitution(self._package) if self._package else None

        if not executable:
            raise RuntimeError("Node executable is required")

        # Find the executable
        cmd = self._find_executable(executable, package, context)

        # Add additional arguments
        for arg in self._arguments:
            arg_str = context.perform_substitution(arg)
            cmd.append(arg_str)

        return cmd

    def _build_environment(self, context: 'LaunchContext') -> Dict[str, str]:
        """Build environment variables for the node."""
        import json

        # Start with current environment or user-specified environment
        if self._node_env:
            env = {}
            for key, value in self._node_env.items():
                env[key] = context.perform_substitution(value) if hasattr(value, 'perform') else str(value)
        else:
            env = os.environ.copy()

        # Add additional environment variables
        if self._node_additional_env:
            for key, value in self._node_additional_env.items():
                env[key] = context.perform_substitution(value) if hasattr(value, 'perform') else str(value)

        # Set node name
        if self._node_name:
            node_name = context.perform_substitution(self._node_name)
            env['LWRCLPY_NODE_NAME'] = node_name

        # Set namespace
        if self._node_namespace:
            namespace = context.perform_substitution(self._node_namespace)
            if namespace:
                env['LWRCLPY_NAMESPACE'] = namespace

        # Set parameters as JSON
        if self._parameters:
            params = {}
            for param in self._parameters:
                if isinstance(param, dict):
                    for key, value in param.items():
                        if hasattr(value, 'perform'):
                            value = context.perform_substitution(value)
                        params[key] = value
            if params:
                env['LWRCLPY_PARAMS'] = json.dumps(params)

        # Set remappings
        if self._remappings:
            remaps = []
            for remap_from, remap_to in self._remappings:
                from_str = context.perform_substitution(remap_from)
                to_str = context.perform_substitution(remap_to)
                remaps.append(f'{from_str}:={to_str}')
            if remaps:
                env['LWRCLPY_REMAPPINGS'] = ';'.join(remaps)

        return env

    def describe(self) -> str:
        """Return a description of this action."""
        parts = ["Node("]
        if self._package:
            parts.append(f"package={self._package}, ")
        if self._node_executable:
            parts.append(f"executable={self._node_executable}, ")
        if self._node_name:
            parts.append(f"name={self._node_name}")
        parts.append(")")
        return ''.join(parts)
