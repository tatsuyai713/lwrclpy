# Copyright (c) 2008 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2009 Willow Garage, Inc. All rights reserved.
# Copyright (c) 2024 Open Source Robotics Foundation, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# See LICENSE in this package and THIRD_PARTY_NOTICES.md for details.

from __future__ import annotations

from threading import Thread
from typing import Optional, Union

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile
from tf2_msgs.msg import TFMessage

from .buffer import Buffer

DEFAULT_STATIC_TF_TOPIC = "/tf_static"


def _get_field(obj, name, default=None):
    val = getattr(obj, name, default)
    if callable(val):
        try:
            return val()
        except TypeError:
            return val
    return val


class StaticTransformListener:
    def __init__(
        self,
        buffer: Buffer,
        node: Node,
        *,
        spin_thread: bool = False,
        static_qos: Optional[Union[QoSProfile, int]] = None,
        tf_static_topic: str = DEFAULT_STATIC_TF_TOPIC,
    ) -> None:
        if static_qos is None:
            static_qos = QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL, history=HistoryPolicy.KEEP_LAST)
        self.buffer = buffer
        self.node = node
        self.group = ReentrantCallbackGroup()
        self.tf_static_sub = node.create_subscription(TFMessage, tf_static_topic, self.static_callback, static_qos, callback_group=self.group)

        if spin_thread:
            self.executor = SingleThreadedExecutor()

            def run_func():
                self.executor.add_node(self.node)
                self.executor.spin()
                self.executor.remove_node(self.node)

            self.dedicated_listener_thread = Thread(target=run_func, daemon=True)
            self.dedicated_listener_thread.start()

    def __del__(self) -> None:
        try:
            if hasattr(self, "dedicated_listener_thread") and hasattr(self, "executor"):
                self.executor.shutdown()
                self.dedicated_listener_thread.join()
            self.unregister()
        except Exception:
            pass

    def unregister(self) -> None:
        self.node.destroy_subscription(self.tf_static_sub)

    def static_callback(self, data: TFMessage) -> None:
        for transform in _get_field(data, "transforms") or []:
            self.buffer.set_transform_static(transform, "default_authority")
