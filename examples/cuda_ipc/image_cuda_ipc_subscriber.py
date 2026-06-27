#!/usr/bin/env python3
"""Receive sensor_msgs/Image and use CUDA IPC metadata when available."""

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
    parser.add_argument("--topic", default="cuda_ipc/image")
    parser.add_argument(
        "--open-cupy",
        action="store_true",
        help="open CUDA IPC memory as a CuPy ndarray when metadata is present",
    )
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("image_cuda_ipc_subscriber")
    qos = QoSProfile(
        depth=2,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
    )

    def on_image(msg: Image):
        width = int(msg.width)
        height = int(msg.height)
        data = msg.data
        if getattr(data, "is_cuda_ipc", False):
            line = (
                f"[recv] {width}x{height} cuda_ipc=True "
                f"shape={data.cuda_ipc_shape} nbytes={len(data)} device={data.cuda_ipc_device_id}"
            )
            if args.open_cupy:
                try:
                    arr = data.open_cupy()
                    line += f" cupy_shape={arr.shape} dtype={arr.dtype}"
                except Exception as exc:
                    line += f" cupy_open_error={exc}"
            print(line)
            return
        print(f"[recv] {width}x{height} cuda_ipc=False ros_payload_bytes={_ros_payload_len(msg)}")

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
