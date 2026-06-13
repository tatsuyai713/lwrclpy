#!/usr/bin/env python3
"""Receive sensor_msgs/Image and use CUDA IPC metadata when available."""

from __future__ import annotations

import argparse

import rclpy
from lwrclpy import data_buffer, get_cuda_buffer
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image


def _get_field(msg, name: str, default=None):
    value = getattr(msg, name, default)
    if callable(value):
        try:
            return value()
        except Exception:
            return default
    return value


def _ros_payload_len(msg: Image) -> int:
    try:
        return data_buffer(msg).nbytes()
    except Exception:
        try:
            return len(_get_field(msg, "data", b""))
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
        width = int(_get_field(msg, "width", 0))
        height = int(_get_field(msg, "height", 0))
        cuda_buf = get_cuda_buffer(msg, "data")
        if cuda_buf is not None:
            line = (
                f"[recv] {width}x{height} cuda_ipc=True "
                f"shape={cuda_buf.shape} nbytes={cuda_buf.nbytes} device={cuda_buf.device_id}"
            )
            if args.open_cupy:
                try:
                    arr = cuda_buf.open_cupy()
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
