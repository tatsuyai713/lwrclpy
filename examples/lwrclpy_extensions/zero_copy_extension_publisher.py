#!/usr/bin/env python3
"""lwrclpy-only zero-copy transport extension example.

This sample verifies that lwrclpy has explicitly enabled Fast DDS DataSharing
for the publisher and subscription.  By default the message is published with the
standard rclpy-compatible publish(msg) API; zero-copy is provided by the Fast DDS
shared-memory/DataSharing transport.  With rebuilt SWIG loan helpers, the sample
can also exercise lwrclpy's experimental loaned-message extension.
"""

import argparse

import rclpy
from lwrclpy.context import try_shutdown
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import Int32


def main():
    parser = argparse.ArgumentParser(description="Verify lwrclpy Fast DDS DataSharing zero-copy")
    parser.add_argument(
        "--require-zero-copy",
        action="store_true",
        help="fail if Fast DDS DataSharing was not enabled",
    )
    parser.add_argument(
        "--require-loaned-message",
        action="store_true",
        help="fail unless the experimental lwrclpy loaned-message path is available and used",
    )
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("zero_copy_extension")
    logger = node.get_logger()
    exit_code = 0

    qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
    pub = node.create_publisher(Int32, "zero_copy_extension", qos)
    received = []

    def on_message(msg: Int32):
        received.append(msg.data)
        logger.info(f"received: {msg.data}")

    sub = node.create_subscription(Int32, "zero_copy_extension", on_message, qos)

    try:
        logger.info("=== lwrclpy Zero-Copy Transport Extension ===")
        logger.info(f"publisher.zero_copy_enabled: {pub.zero_copy_enabled}")
        logger.info(f"subscription.zero_copy_enabled: {sub.zero_copy_enabled}")
        logger.info(f"publisher.can_loan_messages: {pub.can_loan_messages}")

        if args.require_zero_copy and not (pub.zero_copy_enabled and sub.zero_copy_enabled):
            logger.error("Fast DDS DataSharing zero-copy transport is not enabled")
            return 2
        if args.require_loaned_message and not pub.can_loan_messages:
            logger.error("lwrclpy loaned-message extension is not available in these bindings")
            return 3

        if pub.can_loan_messages:
            msg = pub.loan_message(require_zero_copy=args.require_loaned_message)
            msg.data = 42
            pub.publish(msg)
            logger.info("published via lwrclpy loaned-message extension")
        else:
            msg = Int32()
            msg.data = 42
            pub.publish(msg)

        for _ in range(20):
            if received:
                break
            rclpy.spin_once(node, timeout_sec=0.1)

        if not received:
            logger.error("message was not received")
            exit_code = 1
        elif args.require_loaned_message:
            logger.info("Verified lwrclpy loaned-message extension is available")
        elif pub.zero_copy_enabled and sub.zero_copy_enabled:
            logger.info("Verified Fast DDS DataSharing zero-copy transport is enabled")
        else:
            logger.info("Message path works, but DataSharing zero-copy transport is not enabled")
    finally:
        node.destroy_node()
        try_shutdown()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())