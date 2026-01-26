#!/usr/bin/env python3
"""Demonstration of zero-copy publishing using loan_message().

This example shows:
- Using loan_message() for efficient zero-copy publishing
- Context manager pattern for automatic message publishing
- Comparison with regular publish
"""

import time
import rclpy
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("loan_message_publisher")
    logger = node.get_logger()
    
    # Create publisher with reliable QoS
    qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
    pub = node.create_publisher(String, "loan_demo", qos)
    
    logger.info("=== Zero-Copy Publishing Demo ===")
    logger.info("Using loan_message() for efficient publishing\n")
    
    rate = node.create_rate(2.0)  # 2 Hz
    count = 0
    
    try:
        while rclpy.ok() and count < 10:
            # Method 1: Using loan_message() with context manager
            # The message is automatically published when exiting the context
            with pub.loan_message() as msg:
                msg.data = f"Loaned message {count}"
                logger.info(f"[loan_message] Sending: {msg.data}")
            # Message is published here automatically
            
            count += 1
            
            # Method 2: Traditional publish (for comparison)
            msg_traditional = String()
            msg_traditional.data = f"Traditional message {count}"
            pub.publish(msg_traditional)
            logger.info(f"[traditional] Sending: {msg_traditional.data}")
            
            count += 1
            rate.sleep()
        
        logger.info("\n=== Publishing Complete ===")
        logger.info("Note: loan_message() enables zero-copy when Fast DDS")
        logger.info("data sharing is available, reducing memory copies.")
        
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
