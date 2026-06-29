# Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

from __future__ import annotations

from rclpy.duration import Duration

from .buffer_interface import BufferInterface


class BufferClient(BufferInterface):
    """Placeholder for geometry2's action-based BufferClient.

    lwrclpy currently includes the local Buffer/Broadcaster/Listener TF path.
    The action server protocol used by upstream BufferClient requires generated
    tf2 action types that are not part of the bundled Fast DDS IDL set.
    """

    def __init__(self, node, ns: str, check_frequency: float = 10.0, timeout_padding: Duration = Duration(seconds=2.0)) -> None:
        super().__init__()
        self.node = node
        self.ns = ns
        self.check_frequency = check_frequency
        self.timeout_padding = timeout_padding

    def lookup_transform(self, *args, **kwargs):
        raise NotImplementedError("tf2_ros.BufferClient is not available without tf2_msgs/action/LookupTransform")

    def lookup_transform_full(self, *args, **kwargs):
        raise NotImplementedError("tf2_ros.BufferClient is not available without tf2_msgs/action/LookupTransform")

    def can_transform(self, *args, **kwargs) -> bool:
        return False

    def can_transform_full(self, *args, **kwargs) -> bool:
        return False
