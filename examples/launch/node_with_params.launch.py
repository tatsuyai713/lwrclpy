#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Node launch with parameters example (ROS 2 style).

Usage:
    python examples/launch/node_with_params.launch.py
    python examples/launch/node_with_params.launch.py rate:=2.0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'rate',
            default_value='1.0',
            description='Publish rate in Hz'
        ),

        DeclareLaunchArgument(
            'namespace',
            default_value='',
            description='Node namespace'
        ),

        Node(
            package='pubsub/string',
            executable='talker',
            name='talker',
            namespace=LaunchConfiguration('namespace'),
            parameters=[{
                'publish_rate': LaunchConfiguration('rate'),
            }],
            output='screen',
        ),

        Node(
            package='pubsub/string',
            executable='listener',
            name='listener',
            namespace=LaunchConfiguration('namespace'),
            output='screen',
        ),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
