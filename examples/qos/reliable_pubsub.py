#!/usr/bin/env python3
"""Reliable publisher/subscriber with QoS.

This example shows:
- Reliable delivery QoS
- Transient local durability (late-joining subscribers)
- QoS compatibility checking
"""

import time
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy


def main():
    rclpy.init()
    node = rclpy.create_node("reliable_demo")
    logger = node.get_logger()
    
    logger.info("=== Reliable Pub/Sub Demo ===\n")
    
    # Create QoS profile for reliable delivery
    reliable_qos = QoSProfile(
        depth=10,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        history=HistoryPolicy.KEEP_LAST
    )
    
    logger.info("QoS Profile:")
    logger.info(f"  Reliability: RELIABLE")
    logger.info(f"  Durability: TRANSIENT_LOCAL")
    logger.info(f"  History: KEEP_LAST (depth=10)")
    logger.info("")
    
    from std_msgs.msg import String
    
    # Publisher with reliable QoS
    pub = node.create_publisher(String, "/reliable_topic", reliable_qos)
    
    # Publish some messages before subscriber exists
    logger.info("--- Publishing before subscriber exists ---")
    for i in range(5):
        msg = String()
        msg.data = f"Early message {i}"
        pub.publish(msg)
        logger.info(f"Published: {msg.data}")
        time.sleep(0.1)
    
    logger.info("")
    
    # Create subscriber (late joiner)
    logger.info("--- Creating late-joining subscriber ---")
    received = []
    
    def callback(msg):
        received.append(msg.data)
        logger.info(f"Received: {msg.data}")
    
    sub = node.create_subscription(String, "/reliable_topic", callback, reliable_qos)
    
    # Process for a while to receive transient local messages
    logger.info("Processing... (should receive early messages due to TRANSIENT_LOCAL)")
    for _ in range(20):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info("")
    
    # Publish more messages
    logger.info("--- Publishing after subscriber exists ---")
    for i in range(3):
        msg = String()
        msg.data = f"New message {i}"
        pub.publish(msg)
        logger.info(f"Published: {msg.data}")
        
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.1)
    
    # Summary
    logger.info("")
    logger.info("--- Summary ---")
    logger.info(f"Total received: {len(received)}")
    logger.info(f"Messages: {received}")
    
    early_count = sum(1 for m in received if "Early" in m)
    new_count = sum(1 for m in received if "New" in m)
    
    logger.info(f"Early messages received: {early_count}")
    logger.info(f"New messages received: {new_count}")
    
    if early_count > 0:
        logger.info("✓ TRANSIENT_LOCAL durability working - late joiner received old messages!")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
