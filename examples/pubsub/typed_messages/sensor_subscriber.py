#!/usr/bin/env python3
"""Subscribing to sensor messages.

This example shows:
- Receiving sensor_msgs types
- Processing array data
- Analyzing sensor readings
"""

import rclpy
from sensor_msgs.msg import LaserScan, Imu, Range, Temperature


def _call(value, default=None):
    try:
        return value() if callable(value) else value
    except Exception:
        return default


def _number(value, default=0.0):
    try:
        return float(_call(value, default))
    except Exception:
        return default


def _sequence(value):
    value = _call(value, ())
    if value is None:
        return []
    try:
        return list(value)
    except Exception:
        return []


def main():
    rclpy.init()
    node = rclpy.create_node("sensor_subscriber")
    logger = node.get_logger()
    
    logger.info("=== Sensor Messages Subscriber ===\n")
    
    def scan_callback(msg):
        try:
            ranges = [_number(r) for r in _sequence(msg.ranges)]
            range_min = _number(msg.range_min)
            range_max = _number(msg.range_max)
            valid_min = [r for r in ranges if r > range_min]
            valid_max = [r for r in ranges if r < range_max]
            if valid_min and valid_max:
                logger.info(f"[LaserScan] {len(ranges)} readings, "
                           f"min={min(valid_min):.2f}m, max={max(valid_max):.2f}m")
            else:
                logger.info(f"[LaserScan] {len(ranges)} readings")
        except Exception as exc:
            logger.warning(f"[LaserScan] skipped invalid sample: {exc}")
    
    def imu_callback(msg):
        try:
            acc = _call(msg.linear_acceleration)
            gyro = _call(msg.angular_velocity)
            logger.info(f"[IMU] acc=({_number(acc.x):.2f}, {_number(acc.y):.2f}, {_number(acc.z):.2f}), "
                       f"gyro_z={_number(gyro.z):.4f}")
        except Exception as exc:
            logger.warning(f"[IMU] skipped invalid sample: {exc}")
    
    def range_callback(msg):
        try:
            logger.info(f"[Range] distance={_number(msg.range):.3f}m, "
                       f"fov={_number(msg.field_of_view):.2f}rad")
        except Exception as exc:
            logger.warning(f"[Range] skipped invalid sample: {exc}")
    
    def temp_callback(msg):
        try:
            logger.info(f"[Temperature] {_number(msg.temperature):.1f}°C ± {_number(msg.variance):.2f}")
        except Exception as exc:
            logger.warning(f"[Temperature] skipped invalid sample: {exc}")
    
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
