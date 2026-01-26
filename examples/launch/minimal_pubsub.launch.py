#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Minimal pub/sub launch example.

This launch file uses the exact same syntax as ROS 2 launch files.
It can be used in both ROS 2 and lwrclpy environments.

Usage (lwrclpy):
    python examples/launch/minimal_pubsub.launch.py

Usage (ROS 2):
    ros2 launch examples/launch/minimal_pubsub.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'topic',
            default_value='/chatter',
            description='Topic name for pub/sub'
        ),

        # ROS 2 style: package + executable
        # In lwrclpy, package='pubsub.string' maps to examples/pubsub/string/
        Node(
            package='pubsub.string',
            executable='talker',
            name='talker',
            remappings=[('/chatter', LaunchConfiguration('topic'))],
            output='screen',
        ),

        Node(
            package='pubsub.string',
            executable='listener',
            name='listener',
            remappings=[('/chatter', LaunchConfiguration('topic'))],
            output='screen',
        ),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
