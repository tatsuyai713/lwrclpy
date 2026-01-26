#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
OpaqueFunction example (ROS 2 style).

OpaqueFunction allows dynamic launch configuration at runtime.

Usage:
    python examples/launch/opaque_function.launch.py
    python examples/launch/opaque_function.launch.py num_robots:=5
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_setup(context, *args, **kwargs):
    """
    Dynamic setup function executed at launch time.
    
    This has access to resolved LaunchConfiguration values.
    """
    robot_name = LaunchConfiguration('robot_name').perform(context)
    num_robots = int(LaunchConfiguration('num_robots').perform(context))
    
    actions = []
    actions.append(LogInfo(msg=f'Creating {num_robots} robots...'))
    
    for i in range(num_robots):
        node_name = f'{robot_name}_{i}'
        actions.append(
            Node(
                package='pubsub.string',
                executable='talker',
                name=node_name,
                parameters=[{'robot_id': i}],
                remappings=[('/chatter', f'/{node_name}/chatter')],
                output='screen',
            )
        )
    
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('robot_name', default_value='robot'),
        DeclareLaunchArgument('num_robots', default_value='2'),

        LogInfo(msg='OpaqueFunction demo starting...'),
        
        OpaqueFunction(function=launch_setup),
        
        LogInfo(msg='All robots launched!'),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
