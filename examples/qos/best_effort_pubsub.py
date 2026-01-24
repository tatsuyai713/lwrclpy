#!/usr/bin/env python3
"""Best-effort communication (for high-frequency data).

This example shows:
- Best effort reliability (drops messages if needed)
- Volatile durability
- Suitable for sensor data
"""

import time
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy


def main():
    rclpy.init()
    node = rclpy.create_node("best_effort_demo")
    logger = node.get_logger()
    
    logger.info("=== Best Effort Pub/Sub Demo ===\n")
    
    # Create QoS profile for best effort (sensor data)
    best_effort_qos = QoSProfile(
        depth=1,  # Only keep latest
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST
    )
    
    logger.info("QoS Profile:")
    logger.info(f"  Reliability: BEST_EFFORT")
    logger.info(f"  Durability: VOLATILE")
    logger.info(f"  History: KEEP_LAST (depth=1)")
    logger.info("")
    
    from std_msgs.msg import Float32
    
    # High-frequency publisher
    pub = node.create_publisher(Float32, "/sensor_data", best_effort_qos)
    
    # Statistics
    stats = {"sent": 0, "received": 0, "dropped": 0, "last_seq": -1}
    
    def callback(msg):
        stats["received"] += 1
        seq = int(msg.data)
        
        if stats["last_seq"] >= 0:
            expected = stats["last_seq"] + 1
            if seq != expected:
                dropped = seq - expected
                stats["dropped"] += dropped
                logger.warn(f"Dropped {dropped} messages (got {seq}, expected {expected})")
        
        stats["last_seq"] = seq
    
    sub = node.create_subscription(Float32, "/sensor_data", callback, best_effort_qos)
    
    # Allow DDS discovery
    time.sleep(0.5)
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    # Publish at high rate
    logger.info("--- High-frequency publishing (100 Hz for 2 seconds) ---\n")
    
    start = time.monotonic()
    seq = 0
    
    while (time.monotonic() - start) < 2.0:
        msg = Float32()
        msg.data = float(seq)
        pub.publish(msg)
        stats["sent"] += 1
        seq += 1
        
        # Process callbacks occasionally
        if seq % 10 == 0:
            rclpy.spin_once(node, timeout_sec=0.001)
        
        # 100 Hz
        time.sleep(0.01)
    
    # Process remaining
    for _ in range(50):
        rclpy.spin_once(node, timeout_sec=0.01)
    
    # Summary
    logger.info("--- Summary ---")
    logger.info(f"Messages sent: {stats['sent']}")
    logger.info(f"Messages received: {stats['received']}")
    logger.info(f"Messages dropped: {stats['dropped']}")
    
    if stats["sent"] > 0:
        delivery_rate = stats["received"] / stats["sent"] * 100
        logger.info(f"Delivery rate: {delivery_rate:.1f}%")
    
    logger.info("\nNote: BEST_EFFORT may drop messages under load")
    logger.info("This is normal and expected for sensor data")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
