#!/usr/bin/env python3
"""Zero-copy friendly publishing with the standard rclpy publish API.

This example intentionally uses only the portable rclpy API.  lwrclpy enables
Fast DDS DataSharing/SHM internally when available, while ROS 2 rclpy runs the
same code through its configured rmw implementation.
"""

import rclpy
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("zero_copy_publisher")
    logger = node.get_logger()

    qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
    pub = node.create_publisher(String, "loan_demo", qos)

    logger.info("=== Zero-Copy Friendly Publishing Demo ===")
    logger.info("Using standard rclpy publish(); middleware optimizes when available\n")

    rate = node.create_rate(2.0)
    count = 0

    try:
        while rclpy.ok() and count < 10:
            msg = String()
            msg.data = f"Message {count}"
            logger.info(f"[publish] Sending: {msg.data}")
            pub.publish(msg)

            count += 1
            rate.sleep()

        logger.info("\n=== Publishing Complete ===")
        logger.info("The Python API remains rclpy-compatible; zero-copy is a middleware optimization.")

    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()