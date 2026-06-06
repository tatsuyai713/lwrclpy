#!/usr/bin/env python3
"""Benchmark sensor_msgs/Image publish/subscribe throughput in one process."""

from __future__ import annotations

import argparse
import statistics
import time

import rclpy
from lwrclpy.context import try_shutdown
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image


def make_image(payload: bytes, width: int, height: int) -> Image:
    msg = Image()
    msg.height = height
    msg.width = width
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = width * 3
    msg.data = payload
    return msg


def run_case(width: int, height: int, samples: int, *, access_data: bool) -> int:
    rclpy.init()
    node = rclpy.create_node(f"image_fps_benchmark_{width}_{height}")
    topic = f"image_fps_benchmark_{width}_{height}_{time.time_ns()}"
    qos = QoSProfile(
        depth=1,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
    )
    payload = b"\x55" * (width * height * 3)
    sent_ns: list[int] = []
    latency_ms: list[float] = []
    received = 0

    def on_image(msg: Image):
        nonlocal received
        now_ns = time.perf_counter_ns()
        if received < len(sent_ns):
            latency_ms.append((now_ns - sent_ns[received]) / 1_000_000.0)
        if access_data:
            _ = len(msg.data)
        received += 1

    pub = node.create_publisher(Image, topic, qos)
    node.create_subscription(Image, topic, on_image, qos)
    time.sleep(0.1)

    start_ns = time.perf_counter_ns()
    for i in range(samples):
        msg = make_image(payload, width, height)
        sent_ns.append(time.perf_counter_ns())
        pub.publish(msg)
        deadline = time.monotonic() + 1.0
        while received <= i and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.001)
    elapsed_s = (time.perf_counter_ns() - start_ns) / 1_000_000_000.0

    fps = received / elapsed_s if elapsed_s > 0 else 0.0
    p50 = statistics.median(latency_ms) if latency_ms else 0.0
    p95 = statistics.quantiles(latency_ms, n=20)[18] if len(latency_ms) >= 20 else max(latency_ms or [0.0])
    print(
        f"{width}x{height} access_data={access_data} "
        f"received={received}/{samples} elapsed={elapsed_s:.3f}s "
        f"fps={fps:.2f} lat_p50={p50:.2f}ms lat_p95={p95:.2f}ms"
    )

    node.destroy_node()
    try_shutdown()
    return 0 if received == samples else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark sensor_msgs/Image throughput")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--access-data", action="store_true", help="read len(msg.data) in the callback")
    args = parser.parse_args()
    return run_case(args.width, args.height, args.samples, access_data=args.access_data)


if __name__ == "__main__":
    raise SystemExit(main())
