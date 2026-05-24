#!/usr/bin/env python3
"""Subscription with MessageInfo demonstration.

This example shows:
- MessageInfo for accessing message metadata
- Source timestamp and receive timestamp
- Publisher GUID and sequence numbers
"""

import time
import rclpy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("message_info_demo")
    logger = node.get_logger()
    
    logger.info("=== MessageInfo Demo ===\n")
    received = []

    def on_message(msg: String, info=None):
        received.append((msg, info))
        logger.info(f"Received: {msg.data}")
        if info:
            logger.info(f"  Source timestamp: {getattr(info, 'source_timestamp', None)}")
            logger.info(f"  Received timestamp: {getattr(info, 'received_timestamp', None)}")
            logger.info(f"  Publisher GID: {getattr(info, 'publisher_gid', None)}")
            logger.info(f"  Publication sequence: {getattr(info, 'publication_sequence_number', None)}")
        else:
            logger.info("  (MessageInfo not available)")
    
    # Create publisher
    pub = node.create_publisher(String, "/info_demo", 10)
    
    sub = node.create_subscription(String, "/info_demo", on_message, 10)
    
    # Allow time for discovery
    time.sleep(0.5)
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info("--- Publishing Messages ---")
    
    # Publish some messages
    for i in range(5):
        msg = String()
        msg.data = f"Message {i}"
        pub.publish(msg)
        logger.info(f"Published: {msg.data}")
        time.sleep(0.1)
    
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)

    logger.info(f"\nReceived {len(received)} messages via callback")

    logger.info("\n--- More Messages ---")
    
    # Publish more
    for i in range(3):
        msg = String()
        msg.data = f"Batch message {i}"
        pub.publish(msg)
    
    time.sleep(0.2)
    for _ in range(5):
        rclpy.spin_once(node, timeout_sec=0.1)

    logger.info(f"Total received: {len(received)}")
    
    logger.info("\n--- MessageInfo Fields Explanation ---")
    logger.info("""
    MessageInfo provides metadata about received messages:
    
    - source_timestamp: When the message was published
    - received_timestamp: When the message was received by subscriber
    - publisher_gid: Unique identifier of the publisher
    - publication_sequence_number: Sequence number from the publisher
    - reception_sequence_number: Sequence number observed by the subscriber
    - is_valid: Whether the sample is valid data
    
    Note: Some fields may be None depending on QoS settings
    and underlying DDS implementation.
    """)
    
    logger.info("=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
