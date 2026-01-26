#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Environment variables example (ROS 2 style).

Usage:
    python examples/launch/environment.launch.py
    python examples/launch/environment.launch.py log_level:=DEBUG
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    SetEnvironmentVariable,
    LogInfo,
)
from launch.substitutions import (
    LaunchConfiguration,
    EnvironmentVariable,
)
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'log_level',
            default_value='INFO',
            description='Logging level'
        ),

        # Set environment variables (ROS 2 style)
        SetEnvironmentVariable('RCUTILS_LOGGING_SEVERITY', LaunchConfiguration('log_level')),
        SetEnvironmentVariable('MY_ROBOT_ENV', 'lwrclpy_robot'),

        # Log environment
        LogInfo(msg=[
            'Log level: ',
            EnvironmentVariable('RCUTILS_LOGGING_SEVERITY', default_value='not_set'),
        ]),

        # Node with environment (ROS 2 style)
        Node(
            package='pubsub/string',
            executable='talker',
            name='talker',
            output='screen',
            additional_env={
                'NODE_SPECIFIC_VAR': 'talker_value',
            },
        ),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
