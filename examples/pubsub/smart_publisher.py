#!/usr/bin/env python3
"""Publisher with subscription count monitoring.

This example shows:
- get_subscription_count() to monitor subscribers
- assert_liveliness() for manual liveliness assertion
- Waiting for subscribers before publishing
- Publish count tracking
"""

import time
import rclpy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("smart_publisher")
    logger = node.get_logger()
    
    logger.info("=== Smart Publisher Demo ===\n")
    
    # Create publisher
    pub = node.create_publisher(String, "/smart_topic", 10)
    
    # 1. Check subscription count
    logger.info("--- Subscription Count Monitoring ---")
    logger.info(f"Initial subscribers: {pub.get_subscription_count()}")
    
    # Create a subscriber to demonstrate
    received_messages = []
    
    def callback(msg):
        received_messages.append(msg.data)
        logger.info(f"Subscriber received: {msg.data}")
    
    sub = node.create_subscription(String, "/smart_topic", callback, 10)
    
    # Give DDS time to match
    time.sleep(0.5)
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info(f"After creating subscriber: {pub.get_subscription_count()}")
    logger.info("")
    
    # 2. Wait for subscribers pattern
    logger.info("--- Wait for Subscribers Pattern ---")
    
    def wait_for_subscribers(publisher, min_count=1, timeout_sec=5.0):
        """Wait until minimum number of subscribers are connected."""
        start = time.monotonic()
        while publisher.get_subscription_count() < min_count:
            if time.monotonic() - start > timeout_sec:
                return False
            time.sleep(0.1)
        return True
    
    # We already have a subscriber, so this should return immediately
    if wait_for_subscribers(pub):
        logger.info("Subscribers ready, safe to publish!")
    logger.info("")
    
    # 3. Publishing with tracking
    logger.info("--- Publishing with Tracking ---")
    
    for i in range(5):
        msg = String()
        msg.data = f"Message {i}"
        pub.publish(msg)
        logger.info(f"Published message {i} (publish count: {pub._publish_count})")
        
        # Process callbacks
        rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info(f"Total messages published: {pub._publish_count}")
    logger.info(f"Total messages received: {len(received_messages)}")
    logger.info("")
    
    # 4. Liveliness assertion
    logger.info("--- Liveliness Assertion ---")
    logger.info("Asserting liveliness (for QoS policies with manual liveliness)...")
    pub.assert_liveliness()
    logger.info("Liveliness asserted")
    logger.info("")
    
    # 5. Dynamic subscriber handling
    logger.info("--- Dynamic Subscriber Handling ---")
    
    initial_count = pub.get_subscription_count()
    logger.info(f"Subscribers before: {initial_count}")
    
    # Create another subscriber
    sub2 = node.create_subscription(String, "/smart_topic", lambda m: None, 10)
    
    time.sleep(0.5)
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    new_count = pub.get_subscription_count()
    logger.info(f"Subscribers after adding one: {new_count}")
    
    # Destroy one subscriber
    node.destroy_subscription(sub2)
    
    time.sleep(0.5)
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    final_count = pub.get_subscription_count()
    logger.info(f"Subscribers after removing one: {final_count}")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
