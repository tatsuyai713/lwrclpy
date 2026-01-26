#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Conditional launch example (ROS 2 style).

Usage:
    python examples/launch/conditional.launch.py
    python examples/launch/conditional.launch.py use_sim:=true
    python examples/launch/conditional.launch.py debug:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, LogInfo
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # Arguments
        DeclareLaunchArgument('use_sim', default_value='false'),
        DeclareLaunchArgument('debug', default_value='true'),
        DeclareLaunchArgument('num_nodes', default_value='1'),

        # Conditional logging
        LogInfo(
            msg='Debug mode enabled',
            condition=IfCondition(LaunchConfiguration('debug'))
        ),

        # Simulation mode group
        GroupAction(
            condition=IfCondition(LaunchConfiguration('use_sim')),
            actions=[
                LogInfo(msg='Running in SIMULATION mode'),
                Node(
                    package='pubsub.string',
                    executable='talker',
                    name='sim_talker',
                    parameters=[{'sim_mode': True}],
                    output='screen',
                ),
            ]
        ),

        # Real robot mode group
        GroupAction(
            condition=UnlessCondition(LaunchConfiguration('use_sim')),
            actions=[
                LogInfo(msg='Running in REAL mode'),
                Node(
                    package='pubsub.string',
                    executable='talker',
                    name='real_talker',
                    parameters=[{'sim_mode': False}],
                    output='screen',
                ),
            ]
        ),

        # Conditional with PythonExpression (multiple nodes)
        GroupAction(
            condition=IfCondition(PythonExpression([
                LaunchConfiguration('num_nodes'), ' > 1'
            ])),
            actions=[
                LogInfo(msg='Launching additional listener'),
                Node(
                    package='pubsub.string',
                    executable='listener',
                    name='listener',
                    output='screen',
                ),
            ]
        ),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
