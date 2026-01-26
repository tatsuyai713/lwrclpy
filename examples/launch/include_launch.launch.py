#!/usr/bin/env python3
# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""
Include another launch file example (ROS 2 style).

Usage:
    python examples/launch/include_launch.launch.py
"""

import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, ThisLaunchFileDir


def generate_launch_description():
    # Get the directory containing this launch file
    launch_dir = os.path.dirname(os.path.realpath(__file__))
    
    return LaunchDescription([
        DeclareLaunchArgument(
            'included_topic',
            default_value='/included_chatter',
            description='Topic for the included launch'
        ),

        LogInfo(msg='Including minimal_pubsub.launch.py...'),
        
        # Include another launch file with arguments (ROS 2 style)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, 'minimal_pubsub.launch.py')
            ),
            launch_arguments={
                'topic': LaunchConfiguration('included_topic'),
            }.items(),
        ),
        
        LogInfo(msg='Included launch file started!'),
    ])


if __name__ == '__main__':
    from launch import LaunchService
    import sys

    ls = LaunchService(argv=sys.argv)
    ls.include_launch_description(generate_launch_description())
    sys.exit(ls.run())
