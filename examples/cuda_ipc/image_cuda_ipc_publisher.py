#!/usr/bin/env python3
"""Publish sensor_msgs/Image with an optional CUDA IPC side channel.

Run with a CUDA/CuPy environment to share the GPU allocation with lwrclpy
subscribers on the same host.  Without CuPy, this falls back to a normal
ROS-compatible Image publish path.
"""

from __future__ import annotations

import argparse
import time

import rclpy
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


def _fill_ros_payload(msg: Image, payload) -> None:
    msg.data = bytes(payload)


def _make_cuda_frame(width: int, height: int, seq: int):
    try:
        import cupy as cp
    except Exception:
        return None
    frame = cp.empty((height, width, 3), dtype=cp.uint8)
    frame[..., 0] = seq % 256
    frame[..., 1] = (seq * 3) % 256
    frame[..., 2] = 255
    return frame


def _make_cpu_frame(width: int, height: int, seq: int) -> bytes:
    pixel = bytes((seq % 256, (seq * 3) % 256, 255))
    return pixel * (width * height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="cuda_ipc/image")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="skip the normal ROS Image payload when CUDA IPC metadata is published",
    )
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("image_cuda_ipc_publisher")
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
            cuda_frame = _make_cuda_frame(args.width, args.height, seq)
            if cuda_frame is not None:
                if not args.metadata_only:
                    _fill_ros_payload(msg, cuda_frame.get().data)
                used_ipc = pub.publish_cuda(
                    msg,
                    cuda_frame,
                    field="data",
                    publish_ros_payload=True,
                )
                print(f"[send] seq={seq} cuda_ipc={used_ipc} metadata_only={args.metadata_only}")
            else:
                _fill_ros_payload(msg, _make_cpu_frame(args.width, args.height, seq))
                pub.publish(msg)
                print(f"[send] seq={seq} cuda_ipc=False fallback=ros_payload")
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
