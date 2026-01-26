#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Substitutions example (ROS 2 style).

Usage:
    python examples/launch/substitutions.launch.py
    python examples/launch/substitutions.launch.py robot_name:=my_robot
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, ExecuteProcess
from launch.substitutions import (
    LaunchConfiguration,
    EnvironmentVariable,
    PathJoinSubstitution,
    PythonExpression,
    TextSubstitution,
    FindExecutable,
)


def generate_launch_description():
    return LaunchDescription([
        # Arguments
        DeclareLaunchArgument('robot_name', default_value='robot1'),
        DeclareLaunchArgument('base_path', default_value='/tmp'),
        DeclareLaunchArgument('count', default_value='5'),

        # TextSubstitution
        LogInfo(msg=[
            TextSubstitution(text='Robot name: '),
            LaunchConfiguration('robot_name'),
        ]),

        # PathJoinSubstitution
        LogInfo(msg=[
            'Config path: ',
            PathJoinSubstitution([
                LaunchConfiguration('base_path'),
                LaunchConfiguration('robot_name'),
                'config.yaml',
            ]),
        ]),

        # EnvironmentVariable
        LogInfo(msg=[
            'User: ',
            EnvironmentVariable('USER', default_value='unknown'),
        ]),

        # PythonExpression
        LogInfo(msg=[
            'Count doubled: ',
            PythonExpression([LaunchConfiguration('count'), ' * 2']),
        ]),

        # FindExecutable
        LogInfo(msg=[
            'Python executable: ',
            FindExecutable(name='python3'),
        ]),

        # Using substitutions in ExecuteProcess
        ExecuteProcess(
            cmd=[
                FindExecutable(name='echo'),
                'Hello from',
                LaunchConfiguration('robot_name'),
            ],
            output='screen',
        ),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
