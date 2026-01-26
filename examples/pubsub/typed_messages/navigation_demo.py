#!/usr/bin/env python3
"""Using nav_msgs for robot navigation.

This example shows:
- Odometry messages
- Path messages
- OccupancyGrid basics
"""

import math
import rclpy
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion, Twist, Vector3
from builtin_interfaces.msg import Time


def make_stamp(node):
    """Create timestamp from node's clock."""
    now = node.get_clock().now()
    sec, nsec = now.seconds_nanoseconds
    stamp = Time()
    stamp.sec(sec)
    stamp.nanosec(nsec)
    return stamp


def main():
    rclpy.init()
    node = rclpy.create_node("navigation_demo")
    logger = node.get_logger()
    
    logger.info("=== Navigation Messages Demo ===\n")
    
    # Publishers
    pub_odom = node.create_publisher(Odometry, "/odom", 10)
    pub_path = node.create_publisher(Path, "/planned_path", 10)
    
    # Robot state
    x, y, theta = 0.0, 0.0, 0.0
    vx, vth = 0.2, 0.1  # Linear and angular velocity
    
    path_poses = []  # Store poses for path
    
    def timer_callback():
        nonlocal x, y, theta
        
        # Update robot position (simple motion model)
        dt = 0.1
        x += vx * math.cos(theta) * dt
        y += vx * math.sin(theta) * dt
        theta += vth * dt
        
        # 1. Publish Odometry
        odom = Odometry()
        
        header = odom.header()
        header.stamp(make_stamp(node))
        header.frame_id("odom")
        odom.header(header)
        odom.child_frame_id("base_link")
        
        # Pose
        pose = Pose()
        pos = Point()
        pos.x(x)
        pos.y(y)
        pos.z(0.0)
        pose.position(pos)
        
        quat = Quaternion()
        quat.x(0.0)
        quat.y(0.0)
        quat.z(math.sin(theta / 2))
        quat.w(math.cos(theta / 2))
        pose.orientation(quat)
        
        pose_with_cov = odom.pose()
        pose_with_cov.pose(pose)
        odom.pose(pose_with_cov)
        
        # Twist
        twist = Twist()
        linear = Vector3()
        linear.x(vx)
        linear.y(0.0)
        linear.z(0.0)
        twist.linear(linear)
        
        angular = Vector3()
        angular.x(0.0)
        angular.y(0.0)
        angular.z(vth)
        twist.angular(angular)
        
        twist_with_cov = odom.twist()
        twist_with_cov.twist(twist)
        odom.twist(twist_with_cov)
        
        pub_odom.publish(odom)
        
        # 2. Build and publish Path
        pose_stamped = PoseStamped()
        
        ps_header = pose_stamped.header()
        ps_header.stamp(make_stamp(node))
        ps_header.frame_id("odom")
        pose_stamped.header(ps_header)
        pose_stamped.pose(pose)
        
        path_poses.append(pose_stamped)
        
        # Keep only last 100 poses
        if len(path_poses) > 100:
            path_poses.pop(0)
        
        path = Path()
        path_header = path.header()
        path_header.stamp(make_stamp(node))
        path_header.frame_id("odom")
        path.header(path_header)
        path.poses(path_poses)
        pub_path.publish(path)
        
        logger.info(f"[Odom] pos=({x:.2f}, {y:.2f}), theta={theta:.2f}rad, "
                   f"path_len={len(path_poses)}")
    
    timer = node.create_timer(0.1, timer_callback)
    
    logger.info("Publishing navigation messages...")
    logger.info("Topics: /odom (Odometry), /planned_path (Path)")
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
