# Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

from __future__ import annotations

from typing import List, Optional, Union

from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from rclpy.qos import QoSProfile
from tf2_msgs.msg import TFMessage


def _set_field(obj, name, value):
    attr = getattr(obj, name, None)
    if callable(attr):
        try:
            attr(value)
            return True
        except TypeError:
            pass
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


class TransformBroadcaster:
    def __init__(self, node: Node, qos: Optional[Union[QoSProfile, int]] = None) -> None:
        if qos is None:
            qos = QoSProfile(depth=100)
        self.pub_tf = node.create_publisher(TFMessage, "/tf", qos)

    def sendTransform(self, transform: Union[TransformStamped, List[TransformStamped]]) -> None:
        if not isinstance(transform, list):
            transform = list(transform) if hasattr(transform, "__iter__") else [transform]
        msg = TFMessage()
        _set_field(msg, "transforms", transform)
        self.pub_tf.publish(msg)
