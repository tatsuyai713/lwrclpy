#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Timer action example (ROS 2 style).

Demonstrates delayed launch of nodes.

Usage:
    python examples/launch/timer_action.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('delay', default_value='2.0'),

        LogInfo(msg='Launching talker immediately...'),
        
        Node(
            package='pubsub/string',
            executable='talker',
            name='talker',
            output='screen',
        ),

        LogInfo(msg=[
            'Listener will start after ',
            LaunchConfiguration('delay'),
            ' seconds...',
        ]),
        
        # Delayed launch using TimerAction (ROS 2 style)
        TimerAction(
            period=LaunchConfiguration('delay'),
            actions=[
                LogInfo(msg='Timer fired! Starting listener...'),
                Node(
                    package='pubsub/string',
                    executable='listener',
                    name='listener',
                    output='screen',
                ),
            ],
        ),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
