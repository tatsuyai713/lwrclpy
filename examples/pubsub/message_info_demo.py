#!/usr/bin/env python3
"""Subscription with MessageInfo demonstration.

This example shows:
- take() and take_one() for polling-style subscription
- MessageInfo for accessing message metadata
- Source timestamp and receive timestamp
- Publisher GUID and sequence numbers
"""

import time
import rclpy
from lwrclpy.subscription import MessageInfo
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("message_info_demo")
    logger = node.get_logger()
    
    logger.info("=== MessageInfo Demo ===\n")
    
    # Create publisher
    pub = node.create_publisher(String, "/info_demo", 10)
    
    # Create subscription
    sub = node.create_subscription(String, "/info_demo", lambda m: None, 10)
    
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
    
    # Process to ensure messages are received
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info("\n--- Using take_one() ---")
    
    # Take single message with info
    result = sub.take_one()
    if result:
        msg, info = result
        logger.info(f"Received: {msg.data}")
        
        if info:
            logger.info(f"  Source timestamp: {info.source_timestamp}")
            logger.info(f"  Received timestamp: {info.received_timestamp}")
            logger.info(f"  Publisher GUID: {info.publisher_guid}")
            logger.info(f"  Sequence number: {info.sequence_number}")
            logger.info(f"  Sample identity: {info.sample_identity}")
        else:
            logger.info("  (MessageInfo not available)")
    else:
        logger.info("No message available")
    
    logger.info("\n--- Using take() for Multiple Messages ---")
    
    # Publish more
    for i in range(3):
        msg = String()
        msg.data = f"Batch message {i}"
        pub.publish(msg)
    
    time.sleep(0.2)
    for _ in range(5):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    # Take up to 10 messages at once
    messages = sub.take(max_count=10)
    logger.info(f"Took {len(messages)} messages:")
    
    for i, (msg, info) in enumerate(messages):
        logger.info(f"  [{i}] {msg.data}")
        if info and info.sequence_number is not None:
            logger.info(f"      seq={info.sequence_number}")
    
    logger.info("\n--- MessageInfo Fields Explanation ---")
    logger.info("""
    MessageInfo provides metadata about received messages:
    
    - source_timestamp: When the message was published
    - received_timestamp: When the message was received by subscriber
    - publisher_guid: Unique identifier of the publisher
    - sequence_number: Sequence number from the publisher
    - sample_identity: Full sample identity from DDS
    - is_valid: Whether the sample is valid data
    
    Note: Some fields may be None depending on QoS settings
    and underlying DDS implementation.
    """)
    
    logger.info("=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
