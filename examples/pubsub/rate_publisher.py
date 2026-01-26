#!/usr/bin/env python3
"""Rate-based publishing demonstration.

This example shows:
- Using create_rate() for fixed-frequency publishing
- Rate sleep with ROS time
- Comparison with timers
"""

import time
import rclpy
from std_msgs.msg import Int32


def main():
    rclpy.init()
    node = rclpy.create_node("rate_demo")
    logger = node.get_logger()
    
    logger.info("=== Rate-based Publishing Demo ===\n")
    
    pub = node.create_publisher(Int32, "/rate_counter", 10)
    
    # Create rate object for 5 Hz
    rate = node.create_rate(5.0)
    
    logger.info("Publishing at 5 Hz using create_rate()")
    logger.info("Press Ctrl+C to stop\n")
    
    count = 0
    start_time = time.monotonic()
    
    try:
        while rclpy.ok() and count < 50:
            msg = Int32()
            msg.data = count
            pub.publish(msg)
            
            elapsed = time.monotonic() - start_time
            expected = count * 0.2  # 5 Hz = 0.2s period
            drift = elapsed - expected
            
            logger.info(f"Published {count}, elapsed={elapsed:.3f}s, drift={drift*1000:.1f}ms")
            
            count += 1
            rate.sleep()
    
    except KeyboardInterrupt:
        logger.info("\nStopped by user")
    
    finally:
        total_time = time.monotonic() - start_time
        actual_rate = count / total_time if total_time > 0 else 0
        
        logger.info(f"\n--- Summary ---")
        logger.info(f"Messages: {count}")
        logger.info(f"Total time: {total_time:.3f}s")
        logger.info(f"Actual rate: {actual_rate:.2f} Hz (target: 5.0 Hz)")
        
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
