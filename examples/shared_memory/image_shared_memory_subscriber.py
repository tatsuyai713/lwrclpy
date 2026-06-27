#!/usr/bin/env python3
"""Receive sensor_msgs/Image and read CPU shared-memory payloads when present."""

from __future__ import annotations

import argparse

import rclpy
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image


def _ros_payload_len(msg: Image) -> int:
    try:
        return len(msg.data)
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="shared_memory/image")
    parser.add_argument("--read-byte", action="store_true", help="read the first byte from shared memory")
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("image_shared_memory_subscriber")
    qos = QoSProfile(
        depth=2,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
    )

    def on_image(msg: Image):
        width = int(msg.width)
        height = int(msg.height)
        data = msg.data
        shared_memory = bool(getattr(data, "is_shared_memory", False))
        nbytes = len(data) if shared_memory else _ros_payload_len(msg)
        line = f"[recv] {width}x{height} shared_memory={shared_memory} nbytes={nbytes}"
        if args.read_byte:
            first_byte = data[0] if data else None
            line += f" first_byte={first_byte}"
        print(line)

    node.create_subscription(Image, args.topic, on_image, qos)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
