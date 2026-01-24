#!/usr/bin/env python3
"""Subscribing to sensor messages.

This example shows:
- Receiving sensor_msgs types
- Processing array data
- Analyzing sensor readings
"""

import rclpy
from sensor_msgs.msg import LaserScan, Imu, Range, Temperature


def main():
    rclpy.init()
    node = rclpy.create_node("sensor_subscriber")
    logger = node.get_logger()
    
    logger.info("=== Sensor Messages Subscriber ===\n")
    
    def scan_callback(msg):
        ranges = msg.ranges()
        if ranges:
            min_range = min(r for r in ranges if r > msg.range_min())
            max_range = max(r for r in ranges if r < msg.range_max())
            logger.info(f"[LaserScan] {len(ranges)} readings, "
                       f"min={min_range:.2f}m, max={max_range:.2f}m")
    
    def imu_callback(msg):
        ori = msg.orientation()
        acc = msg.linear_acceleration()
        gyro = msg.angular_velocity()
        logger.info(f"[IMU] acc=({acc.x():.2f}, {acc.y():.2f}, {acc.z():.2f}), "
                   f"gyro_z={gyro.z():.4f}")
    
    def range_callback(msg):
        logger.info(f"[Range] distance={msg.range_():.3f}m, "
                   f"fov={msg.field_of_view():.2f}rad")
    
    def temp_callback(msg):
        logger.info(f"[Temperature] {msg.temperature():.1f}°C ± {msg.variance():.2f}")
    
    # Create subscriptions
    sub_scan = node.create_subscription(LaserScan, "/scan", scan_callback, 10)
    sub_imu = node.create_subscription(Imu, "/imu/data", imu_callback, 10)
    sub_range = node.create_subscription(Range, "/sonar", range_callback, 10)
    sub_temp = node.create_subscription(Temperature, "/temperature", temp_callback, 10)
    
    logger.info("Subscribing to sensor topics...")
    logger.info("Run sensor_publisher.py in another terminal")
    logger.info("Press Ctrl+C to stop\n")
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        logger.info("\nStopping...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
