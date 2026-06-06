#!/usr/bin/env python3
"""Benchmark automatic lwrclpy zero-copy with a large fixed-size payload."""

from __future__ import annotations

import argparse
import statistics
import time

import rclpy
from lwrclpy.context import try_shutdown
from lwrclpy.message_utils import _assign
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from lwrclpy_bench.msg import LargeFixedImage


PAYLOAD_SIZE = 2_073_600  # 1920x1080 mono8 equivalent; fixed array in LargeFixedImage.idl.


def _set_payload(msg: LargeFixedImage, payload: bytes | None, *, seq: int) -> None:
    _assign(msg, "seq", seq)
    if payload is not None:
        _assign(msg, "data", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Large payload lwrclpy zero-copy benchmark")
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--max-inflight", type=int, default=8)
    parser.add_argument("--poll-timeout", type=float, default=5.0)
    parser.add_argument("--min-mib-s", type=float, default=0.0)
    parser.add_argument(
        "--fill-payload",
        action="store_true",
        help="write the full 2 MiB byte array for every sample; useful to measure Python fill cost",
    )
    parser.add_argument("--require-complete-zero-copy", action="store_true", default=True)
    args = parser.parse_args()

    if args.samples <= 0:
        raise SystemExit("--samples must be positive")

    total_samples = args.samples + max(0, args.warmup)
    payload = (b"\x5a" * PAYLOAD_SIZE) if args.fill_payload else None

    rclpy.init()
    node = rclpy.create_node("large_payload_zero_copy_benchmark")
    logger = node.get_logger()
    qos = QoSProfile(depth=max(16, args.max_inflight * 2), reliability=QoSReliabilityPolicy.RELIABLE)
    pub = node.create_publisher(LargeFixedImage, "large_payload_zero_copy_benchmark", qos)
    sub = node.create_subscription(LargeFixedImage, "large_payload_zero_copy_benchmark", lambda _msg: None, qos)

    sent_times: dict[int, int] = {}
    received = 0
    measured_received = 0
    measured_bytes = 0
    latencies_ms: list[float] = []
    first_measured_send_ns = 0
    last_measured_ns = 0

    def on_message(sample: LargeFixedImage):
        nonlocal received, measured_received, measured_bytes, last_measured_ns
        now_ns = time.perf_counter_ns()
        seq = int(sample.seq())
        sent_ns = sent_times.pop(seq, None)
        if received >= args.warmup:
            last_measured_ns = now_ns
            measured_received += 1
            measured_bytes += PAYLOAD_SIZE
            if sent_ns is not None:
                latencies_ms.append((now_ns - sent_ns) / 1_000_000.0)
        received += 1

    try:
        logger.info("=== lwrclpy Large Payload Zero-Copy Benchmark ===")
        logger.info(f"payload: {PAYLOAD_SIZE / (1024 * 1024):.2f} MiB fixed array")
        logger.info(f"samples: measured={args.samples}, warmup={args.warmup}, total={total_samples}")
        logger.info("message type: lwrclpy_bench/msg/LargeFixedImage")
        logger.info(f"fill_payload: {args.fill_payload}")
        logger.info(f"publisher internal DataSharing: {pub._data_sharing_enabled}")
        logger.info(f"subscription internal DataSharing: {sub._data_sharing_enabled}")
        logger.info(f"publisher internal automatic loan: {pub._automatic_loaned_publish_enabled}")
        logger.info(f"subscription internal automatic loan: {sub._automatic_loaned_receive_enabled}")

        if args.require_complete_zero_copy:
            if not (pub._data_sharing_enabled and sub._data_sharing_enabled):
                logger.error("DataSharing zero-copy transport is not enabled")
                return 2
            if not pub._automatic_loaned_publish_enabled:
                logger.error("Automatic DataWriter loan path is not available")
                return 3
            if not sub._automatic_loaned_receive_enabled:
                logger.error("Automatic DataReader loan path is not available")
                return 4

        node.destroy_subscription(sub)
        sub = node.create_subscription(LargeFixedImage, "large_payload_zero_copy_benchmark", on_message, qos)

        start_ns = time.perf_counter_ns()
        next_seq = 0
        deadline_ns = start_ns + int(args.poll_timeout * 1_000_000_000)

        while received < total_samples:
            while next_seq < total_samples and (next_seq - received) < args.max_inflight:
                msg = LargeFixedImage()
                _set_payload(msg, payload, seq=next_seq)
                if next_seq == args.warmup:
                    first_measured_send_ns = time.perf_counter_ns()
                sent_times[next_seq] = time.perf_counter_ns()
                pub.publish(msg)
                next_seq += 1

            before = received
            rclpy.spin_once(node, timeout_sec=0.01)
            if received > before:
                deadline_ns = time.perf_counter_ns() + int(args.poll_timeout * 1_000_000_000)
                continue

            if time.perf_counter_ns() > deadline_ns:
                logger.error(f"Timed out waiting for samples: received={received}/{total_samples}")
                return 5

        elapsed_s = max((last_measured_ns - first_measured_send_ns) / 1_000_000_000.0, 1e-9)
        mib = measured_bytes / (1024 * 1024)
        throughput = mib / elapsed_s
        lat_avg = statistics.mean(latencies_ms) if latencies_ms else 0.0
        lat_p50 = statistics.median(latencies_ms) if latencies_ms else 0.0
        lat_p95 = statistics.quantiles(latencies_ms, n=20)[18] if len(latencies_ms) >= 20 else max(latencies_ms or [0.0])

        logger.info(f"received measured samples: {measured_received}/{args.samples}")
        logger.info(f"transferred measured payload: {mib:.2f} MiB")
        logger.info(f"throughput: {throughput:.2f} MiB/s")
        logger.info(f"latency ms: avg={lat_avg:.3f}, p50={lat_p50:.3f}, p95={lat_p95:.3f}")
        logger.info(f"publisher internal auto loan count: {pub._auto_loan_publish_count}")
        logger.info(f"subscription internal auto loan count: {sub._auto_loan_receive_count}")
        logger.info("Verified large-payload automatic zero-copy path through normal rclpy-style APIs")

        if args.require_complete_zero_copy:
            if pub._auto_loan_publish_count < total_samples:
                logger.error("Automatic DataWriter loaning was not used for every sample")
                return 7
            if sub._auto_loan_receive_count < total_samples:
                logger.error("Automatic DataReader loaning was not used for every sample")
                return 8

        if args.min_mib_s and throughput < args.min_mib_s:
            logger.error(f"Throughput below threshold: {throughput:.2f} < {args.min_mib_s:.2f} MiB/s")
            return 6
        return 0
    finally:
        node.destroy_node()
        try_shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
