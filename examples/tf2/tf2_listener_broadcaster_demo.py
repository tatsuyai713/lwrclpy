#!/usr/bin/env python3
"""Publish and receive a TF transform with the lwrclpy tf2_ros package."""

import time

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformBroadcaster, TransformListener


def make_transform():
    msg = TransformStamped()
    msg.header.frame_id = "world"
    msg.child_frame_id = "camera"
    msg.transform.translation.x = 1.0
    msg.transform.translation.y = 2.0
    msg.transform.translation.z = 3.0
    msg.transform.rotation.w = 1.0
    return msg


def main():
    rclpy.init()
    node = Node("tf2_listener_broadcaster_demo")
    buffer = Buffer(node=node)
    listener = TransformListener(buffer, node)
    broadcaster = TransformBroadcaster(node)

    try:
        broadcaster.sendTransform(make_transform())
        deadline = time.monotonic() + 5.0
        result = None
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if buffer.can_transform("world", "camera", Time()):
                result = buffer.lookup_transform("world", "camera", Time())
                break
        if result is None:
            raise RuntimeError("Timed out waiting for TF transform")
        print(f"TF OK: camera -> world x={result.transform.translation.x}")
    finally:
        listener.unregister()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
