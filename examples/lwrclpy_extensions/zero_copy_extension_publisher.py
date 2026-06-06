#!/usr/bin/env python3
"""lwrclpy automatic zero-copy transport example.

This sample verifies that lwrclpy has explicitly enabled Fast DDS DataSharing
for the publisher and subscription.  By default the message is published with the
standard rclpy-compatible publish(msg) API; zero-copy is provided by the Fast DDS
shared-memory/DataSharing transport and automatic middleware loaning for fixed
size message types.
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
        "--require-automatic-loan",
        action="store_true",
        help="fail unless automatic internal middleware loaning is available and used",
    )
    parser.add_argument(
        "--require-complete-zero-copy",
        action="store_true",
        help="fail unless DataSharing and automatic internal middleware loaning are used",
    )
    args = parser.parse_args()
    if args.require_complete_zero_copy:
        args.require_zero_copy = True
        args.require_automatic_loan = True

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
        logger.info(f"publisher internal DataSharing: {pub._data_sharing_enabled}")
        logger.info(f"subscription internal DataSharing: {sub._data_sharing_enabled}")
        logger.info(f"publisher internal automatic loan: {pub._automatic_loaned_publish_enabled}")
        logger.info(f"subscription internal automatic loan: {sub._automatic_loaned_receive_enabled}")

        if args.require_zero_copy and not (pub._data_sharing_enabled and sub._data_sharing_enabled):
            logger.error("Fast DDS DataSharing zero-copy transport is not enabled")
            return 2
        if args.require_automatic_loan and not (
            pub._automatic_loaned_publish_enabled and sub._automatic_loaned_receive_enabled
        ):
            logger.error("Automatic internal middleware loaning is not available")
            return 3

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
        elif args.require_complete_zero_copy:
            if pub._auto_loan_publish_count < 1 or sub._auto_loan_receive_count < 1:
                logger.error("Automatic internal loaning was not used")
                return 4
            logger.info("Verified complete automatic zero-copy path through normal rclpy-style APIs")
        elif pub._data_sharing_enabled and sub._data_sharing_enabled:
            logger.info("Verified Fast DDS DataSharing zero-copy transport is enabled")
        else:
            logger.info("Message path works, but DataSharing zero-copy transport is not enabled")
    finally:
        node.destroy_node()
        try_shutdown()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
