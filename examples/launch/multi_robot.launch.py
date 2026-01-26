#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Multiple namespaces example (ROS 2 style).

Demonstrates launching multiple instances with different namespaces.

Usage:
    python examples/launch/multi_robot.launch.py
    python examples/launch/multi_robot.launch.py num_robots:=3
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_robots(context, *args, **kwargs):
    """Generate robot nodes dynamically."""
    num = int(LaunchConfiguration('num_robots').perform(context))
    
    actions = []
    for i in range(num):
        ns = f'robot{i}'
        actions.extend([
            LogInfo(msg=f'Launching robot in namespace: {ns}'),
            Node(
                package='pubsub/string',
                executable='talker',
                name='talker',
                namespace=ns,
                remappings=[('/chatter', 'local_chatter')],
                output='screen',
            ),
            Node(
                package='pubsub/string',
                executable='listener',
                name='listener',
                namespace=ns,
                remappings=[('/chatter', 'local_chatter')],
                output='screen',
            ),
        ])
    
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'num_robots',
            default_value='2',
            description='Number of robot instances'
        ),

        LogInfo(msg='Multi-robot launch starting...'),
        
        OpaqueFunction(function=generate_robots),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
