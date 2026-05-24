#!/usr/bin/env python3
"""Callback-based subscription for zero-copy friendly publishers.

This example shows:
- Receiving messages with a standard rclpy subscription callback
- Reading MessageInfo when the implementation provides it
"""

import rclpy
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("callback_subscriber")
    logger = node.get_logger()
    
    qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
    message_count = 0

    def on_message(msg: String, info=None):
        nonlocal message_count
        message_count += 1
        logger.info(f"Message {message_count}: {msg.data}")
        if info is not None:
            logger.info(f"  Source timestamp: {getattr(info, 'source_timestamp', None)} ns")
            logger.info(f"  Pub sequence: {getattr(info, 'publication_sequence_number', None)}")

    node.create_subscription(String, "loan_demo", on_message, qos)

    logger.info("=== Callback Subscription Demo ===")
    logger.info("Waiting for messages... (run zero_copy_publisher.py)\n")

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)

    except KeyboardInterrupt:
        logger.info(f"\nTotal messages received: {message_count}")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
