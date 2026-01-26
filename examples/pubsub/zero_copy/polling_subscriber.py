#!/usr/bin/env python3
"""Demonstration of polling-based subscription using take().

This example shows:
- Using take() and take_one() for manual message retrieval
- MessageInfo for accessing metadata (timestamps, sequence numbers)
- Polling pattern vs callback pattern
"""

import rclpy
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("polling_subscriber")
    logger = node.get_logger()
    
    # Create subscription (callback will also work, but we'll use polling)
    qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
    
    # Even with polling, we need a callback (can be empty)
    def empty_callback(msg):
        pass
    
    sub = node.create_subscription(String, "loan_demo", empty_callback, qos)
    
    logger.info("=== Polling Subscription Demo ===")
    logger.info("Using take() for manual message retrieval\n")
    logger.info("Waiting for messages... (run loan_message_publisher.py)\n")
    
    message_count = 0
    
    try:
        while rclpy.ok():
            # Method 1: Take a single message
            result = sub.take_one()
            if result is not None:
                msg, info = result
                message_count += 1
                logger.info(f"[take_one] Message {message_count}:")
                logger.info(f"  Data: {msg.data}")
                logger.info(f"  Source timestamp: {info.source_timestamp} ns")
                logger.info(f"  Pub sequence: {info.publication_sequence_number}")
                logger.info("")
            
            # Method 2: Take multiple messages at once
            results = sub.take(max_count=5)
            for msg, info in results:
                message_count += 1
                logger.info(f"[take batch] Message {message_count}: {msg.data}")
            
            # Check publisher count
            pub_count = sub.get_publisher_count()
            if pub_count > 0 and message_count == 0:
                logger.info(f"Connected to {pub_count} publisher(s), waiting for data...")
            
            # Small sleep to avoid busy loop
            node.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info(f"\nTotal messages received via polling: {message_count}")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
