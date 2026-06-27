#!/usr/bin/env python3
"""Publishing sensor messages (LaserScan, Imu, Range, etc.).

This example shows:
- Working with sensor_msgs types
- Array fields in messages
- Header timestamps
"""

import math
import random
import rclpy
from sensor_msgs.msg import LaserScan, Imu, Range, Temperature
from builtin_interfaces.msg import Time
from std_msgs.msg import Header


def make_stamp(node):
    """Create timestamp from node's clock."""
    now = node.get_clock().now()
    sec, nsec = now.seconds_nanoseconds
    stamp = Time()
    stamp.sec(sec)
    stamp.nanosec(nsec)
    return stamp


def make_header(node, frame_id):
    header = Header()
    header.stamp(make_stamp(node))
    header.frame_id(frame_id)
    return header


def main():
    rclpy.init()
    node = rclpy.create_node("sensor_publisher")
    logger = node.get_logger()
    
    logger.info("=== Sensor Messages Publisher ===\n")
    
    # Create publishers
    pub_scan = node.create_publisher(LaserScan, "/scan", 10)
    pub_imu = node.create_publisher(Imu, "/imu/data", 10)
    pub_range = node.create_publisher(Range, "/sonar", 10)
    pub_temp = node.create_publisher(Temperature, "/temperature", 10)
    
    # Simulation state
    scan_count = 0
    
    def timer_callback():
        nonlocal scan_count
        scan_count += 1
        
        # 1. Publish LaserScan
        scan = LaserScan()
        
        scan.header(make_header(node, "laser_frame"))
        
        scan.angle_min(-math.pi / 2)  # -90 degrees
        scan.angle_max(math.pi / 2)   # +90 degrees
        scan.angle_increment(math.pi / 180)  # 1 degree
        scan.time_increment(0.0001)
        scan.scan_time(0.1)
        scan.range_min(0.1)
        scan.range_max(10.0)
        
        # Generate ranges with some noise
        num_readings = 180
        ranges = []
        intensities = []
        for i in range(num_readings):
            # Simulate obstacle at varying distances
            base_range = 3.0 + math.sin(i * 0.1 + scan_count * 0.1) * 1.0
            ranges.append(base_range + random.uniform(-0.05, 0.05))
            intensities.append(random.uniform(0.5, 1.0))
        
        scan.ranges(ranges)
        scan.intensities(intensities)
        pub_scan.publish(scan)
        
        # 2. Publish IMU
        imu = Imu()
        
        imu.header(make_header(node, "imu_frame"))
        
        # Orientation (quaternion)
        from geometry_msgs.msg import Quaternion, Vector3
        quat = Quaternion()
        yaw = scan_count * 0.01
        quat.x(0.0)
        quat.y(0.0)
        quat.z(math.sin(yaw / 2))
        quat.w(math.cos(yaw / 2))
        imu.orientation(quat)
        
        # Angular velocity
        angular = Vector3()
        angular.x(0.0)
        angular.y(0.0)
        angular.z(0.01 + random.uniform(-0.001, 0.001))
        imu.angular_velocity(angular)
        
        # Linear acceleration
        linear = Vector3()
        linear.x(random.uniform(-0.1, 0.1))
        linear.y(random.uniform(-0.1, 0.1))
        linear.z(9.81 + random.uniform(-0.05, 0.05))
        imu.linear_acceleration(linear)
        
        pub_imu.publish(imu)
        
        # 3. Publish Range (ultrasonic sonar)
        sonar = Range()
        
        sonar.header(make_header(node, "sonar_frame"))
        
        sonar.radiation_type(0)  # ULTRASOUND
        sonar.field_of_view(0.5)  # 30 degrees
        sonar.min_range(0.02)
        sonar.max_range(4.0)
        sonar.range(1.5 + random.uniform(-0.05, 0.05))
        pub_range.publish(sonar)
        
        # 4. Publish Temperature
        temp = Temperature()
        
        temp.header(make_header(node, "temp_sensor"))
        
        temp.temperature(25.0 + math.sin(scan_count * 0.1) * 2.0)
        temp.variance(0.1)
        pub_temp.publish(temp)
        
        logger.info(f"Published sensor data #{scan_count}")
    
    timer = node.create_timer(0.1, timer_callback)  # 10 Hz
    
    logger.info("Publishing sensor messages at 10 Hz...")
    logger.info("Topics: /scan, /imu/data, /sonar, /temperature")
    logger.info("Press Ctrl+C to stop\n")
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        logger.info("\nStopping...")
    finally:
        timer.cancel()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
