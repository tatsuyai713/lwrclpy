#!/usr/bin/env python3
"""Subscribing to geometry messages.

This example shows:
- Receiving geometry_msgs types
- Extracting nested message fields
- Multi-topic subscription
"""

import rclpy
from geometry_msgs.msg import Point, Pose, PoseStamped, Twist


def main():
    rclpy.init()
    node = rclpy.create_node("geometry_subscriber")
    logger = node.get_logger()
    
    logger.info("=== Geometry Messages Subscriber ===\n")
    
    def point_callback(msg):
        logger.info(f"[Point] x={msg.x():.3f}, y={msg.y():.3f}, z={msg.z():.3f}")
    
    def pose_callback(msg):
        pos = msg.position()
        ori = msg.orientation()
        logger.info(f"[Pose] pos=({pos.x():.2f}, {pos.y():.2f}, {pos.z():.2f}), "
                   f"ori=(x={ori.x():.3f}, y={ori.y():.3f}, z={ori.z():.3f}, w={ori.w():.3f})")
    
    def twist_callback(msg):
        lin = msg.linear()
        ang = msg.angular()
        logger.info(f"[Twist] linear=({lin.x():.2f}, {lin.y():.2f}, {lin.z():.2f}), "
                   f"angular=({ang.x():.2f}, {ang.y():.2f}, {ang.z():.2f})")
    
    def pose_stamped_callback(msg):
        header = msg.header()
        pose = msg.pose()
        pos = pose.position()
        stamp = header.stamp()
        logger.info(f"[PoseStamped] frame={header.frame_id()}, "
                   f"time={stamp.sec()}.{stamp.nanosec():09d}, "
                   f"pos=({pos.x():.2f}, {pos.y():.2f})")
    
    # Create subscriptions
    sub_point = node.create_subscription(Point, "/position", point_callback, 10)
    sub_pose = node.create_subscription(Pose, "/robot_pose", pose_callback, 10)
    sub_twist = node.create_subscription(Twist, "/cmd_vel", twist_callback, 10)
    sub_pose_stamped = node.create_subscription(PoseStamped, "/goal_pose", pose_stamped_callback, 10)
    
    logger.info("Subscribing to geometry topics...")
    logger.info("Run geometry_publisher.py in another terminal")
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
