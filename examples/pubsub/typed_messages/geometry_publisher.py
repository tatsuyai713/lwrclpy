#!/usr/bin/env python3
"""Publishing geometry messages (Point, Pose, Twist, etc.).

This example shows:
- Working with geometry_msgs types
- Nested message structures
- Publishing complex message types
"""

import math
import rclpy
from geometry_msgs.msg import Point, Pose, PoseStamped, Twist, Vector3, Quaternion


def main():
    rclpy.init()
    node = rclpy.create_node("geometry_publisher")
    logger = node.get_logger()
    
    logger.info("=== Geometry Messages Publisher ===\n")
    
    # Create publishers for different message types
    pub_point = node.create_publisher(Point, "/position", 10)
    pub_pose = node.create_publisher(Pose, "/robot_pose", 10)
    pub_twist = node.create_publisher(Twist, "/cmd_vel", 10)
    pub_pose_stamped = node.create_publisher(PoseStamped, "/goal_pose", 10)
    
    # Simulation state
    angle = 0.0
    radius = 2.0
    
    def timer_callback():
        nonlocal angle
        
        # 1. Publish Point - circular motion
        point = Point()
        point.x(radius * math.cos(angle))
        point.y(radius * math.sin(angle))
        point.z(0.0)
        pub_point.publish(point)
        
        # 2. Publish Pose - position + orientation
        pose = Pose()
        
        # Position
        position = Point()
        position.x(radius * math.cos(angle))
        position.y(radius * math.sin(angle))
        position.z(0.0)
        pose.position(position)
        
        # Orientation (quaternion from yaw angle)
        quat = Quaternion()
        quat.x(0.0)
        quat.y(0.0)
        quat.z(math.sin(angle / 2))
        quat.w(math.cos(angle / 2))
        pose.orientation(quat)
        pub_pose.publish(pose)
        
        # 3. Publish Twist - velocity command
        twist = Twist()
        
        # Linear velocity
        linear = Vector3()
        linear.x(0.5)  # Forward velocity
        linear.y(0.0)
        linear.z(0.0)
        twist.linear(linear)
        
        # Angular velocity
        angular = Vector3()
        angular.x(0.0)
        angular.y(0.0)
        angular.z(0.1)  # Rotation velocity
        twist.angular(angular)
        pub_twist.publish(twist)
        
        # 4. Publish PoseStamped - with timestamp
        pose_stamped = PoseStamped()
        
        # Header with timestamp
        from builtin_interfaces.msg import Time
        header = pose_stamped.header()
        now = node.get_clock().now()
        sec, nsec = now.seconds_nanoseconds
        stamp = Time()
        stamp.sec(sec)
        stamp.nanosec(nsec)
        header.stamp(stamp)
        header.frame_id("map")
        pose_stamped.header(header)
        
        # Goal pose (slightly ahead)
        goal = Pose()
        goal_pos = Point()
        goal_pos.x(radius * math.cos(angle + 0.5))
        goal_pos.y(radius * math.sin(angle + 0.5))
        goal_pos.z(0.0)
        goal.position(goal_pos)
        goal.orientation(quat)
        pose_stamped.pose(goal)
        pub_pose_stamped.publish(pose_stamped)
        
        # Log summary
        logger.info(f"Published: angle={angle:.2f} rad, "
                   f"pos=({point.x():.2f}, {point.y():.2f})")
        
        angle += 0.1
        if angle > 2 * math.pi:
            angle -= 2 * math.pi
    
    timer = node.create_timer(0.2, timer_callback)
    
    logger.info("Publishing geometry messages...")
    logger.info("Topics: /position (Point), /robot_pose (Pose), "
               "/cmd_vel (Twist), /goal_pose (PoseStamped)")
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
