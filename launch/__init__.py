# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
lwrclpy Launch System - ROS 2 Launch compatible implementation.

This module provides a launch system compatible with ROS 2's launch framework,
allowing you to use existing ROS 2 launch files without modification.
"""

from .launch_description import LaunchDescription, LaunchDescriptionEntity
from .launch_service import LaunchService
from .launch_context import LaunchContext
from .actions.include_launch_description import (
    LaunchDescriptionSource,
    PythonLaunchDescriptionSource,
    AnyLaunchDescriptionSource,
)

from . import actions
from . import substitutions
from . import conditions

# Re-export commonly used items
from .actions import (
    Action,
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
    LogInfo,
    SetEnvironmentVariable,
    TimerAction,
    RegisterEventHandler,
    OpaqueFunction,
    SetLaunchConfiguration,
    Shutdown,
)

from .substitutions import (
    Substitution,
    LaunchConfiguration,
    EnvironmentVariable,
    TextSubstitution,
    PathJoinSubstitution,
    PythonExpression,
    FindExecutable,
    Command,
    LocalSubstitution,
    NotSubstitution,
    AndSubstitution,
    OrSubstitution,
)

from .conditions import (
    Condition,
    IfCondition,
    UnlessCondition,
    LaunchConfigurationEquals,
    LaunchConfigurationNotEquals,
)

__all__ = [
    'LaunchDescription',
    'LaunchDescriptionEntity',
    'LaunchService',
    'LaunchContext',
    'LaunchDescriptionSource',
    'PythonLaunchDescriptionSource',
    'AnyLaunchDescriptionSource',
    'actions',
    'substitutions',
    'conditions',
    # Actions
    'Action',
    'DeclareLaunchArgument',
    'ExecuteProcess',
    'GroupAction',
    'IncludeLaunchDescription',
    'LogInfo',
    'SetEnvironmentVariable',
    'TimerAction',
    'RegisterEventHandler',
    'OpaqueFunction',
    'SetLaunchConfiguration',
    'Shutdown',
    # Substitutions
    'Substitution',
    'LaunchConfiguration',
    'EnvironmentVariable',
    'TextSubstitution',
    'PathJoinSubstitution',
    'PythonExpression',
    'FindExecutable',
    'Command',
    'LocalSubstitution',
    'NotSubstitution',
    'AndSubstitution',
    'OrSubstitution',
    # Conditions
    'Condition',
    'IfCondition',
    'UnlessCondition',
    'LaunchConfigurationEquals',
    'LaunchConfigurationNotEquals',
]
