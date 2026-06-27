#!/usr/bin/env python3
"""Publish sensor_msgs/Image with a CPU shared-memory side channel."""

from __future__ import annotations

import argparse

import rclpy
from lwrclpy import data_buffer
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image


def _make_image(width: int, height: int) -> Image:
    msg = Image()
    msg.height = height
    msg.width = width
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = width * 3
    return msg


def _make_frame(width: int, height: int, seq: int) -> bytes:
    pixel = bytes((seq % 256, (seq * 3) % 256, 255))
    return pixel * (width * height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="shared_memory/image")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument(
        "--data-buffer",
        action="store_true",
        help="assign Image.data through lwrclpy.data_buffer() instead of normal msg.data = frame",
    )
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("image_shared_memory_publisher")
    qos = QoSProfile(
        depth=2,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
    )
    pub = node.create_publisher(Image, args.topic, qos)
    rate = node.create_rate(args.rate)
    seq = 0

    try:
        while rclpy.ok():
            msg = _make_image(args.width, args.height)
            frame = _make_frame(args.width, args.height, seq)
            if args.data_buffer:
                data_buffer(msg).assign(frame)
            else:
                msg.data = frame
            pub.publish(msg)
            print(f"[send] seq={seq} bytes={len(frame)} stats={pub.performance_stats}")
            seq += 1
            rate.sleep()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
