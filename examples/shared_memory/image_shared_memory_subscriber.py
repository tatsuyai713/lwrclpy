#!/usr/bin/env python3
"""Receive sensor_msgs/Image and read CPU shared-memory payloads when present."""

from __future__ import annotations

import argparse

import rclpy
from lwrclpy import data_buffer, get_shared_memory_buffer
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
        width = int(_get_field(msg, "width", 0))
        height = int(_get_field(msg, "height", 0))
        shm_buf = get_shared_memory_buffer(msg, "data")
        if shm_buf is not None:
            data = _get_field(msg, "data", b"")
            line = f"[recv] {width}x{height} shared_memory=True nbytes={len(data)} name={shm_buf.name}"
            if args.read_byte:
                first_byte = None
                try:
                    first_byte = data[0] if data else None
                finally:
                    release = getattr(data, "release", None)
                    if callable(release):
                        release()
                    data = None
                    shm_buf.close()
                line += f" first_byte={first_byte}"
            print(line)
            return
        print(f"[recv] {width}x{height} shared_memory=False ros_payload_bytes={_ros_payload_len(msg)}")

    node.create_subscription(Image, args.topic, on_image, qos, fast_callback=True, expose_fields=False)
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
