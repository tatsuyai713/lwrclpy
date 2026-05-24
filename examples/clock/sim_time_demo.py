#!/usr/bin/env python3
"""ROS time clock demonstration.

This example shows:
- Constructing ROS time values
- Comparing ROS time with system time
- Converting time and duration messages
"""

import time
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.duration import Duration
from rclpy.time import Time


def main():
    rclpy.init()
    node = rclpy.create_node("sim_time_demo")
    logger = node.get_logger()
    
    logger.info("=== ROS Time Demo ===\n")
    
    # Create ROS time clock
    ros_clock = Clock(clock_type=ClockType.ROS_TIME)
    
    # System clock for comparison
    system_clock = Clock(clock_type=ClockType.SYSTEM_TIME)
    
    logger.info("--- ROS and System Clocks ---")
    
    sys_now = system_clock.now()
    ros_now = ros_clock.now()
    
    logger.info(f"System time: {sys_now}")
    logger.info(f"ROS time: {ros_now}")
    logger.info("ROS time follows system time unless a /clock source is configured by ROS 2.")
    logger.info("")
    
    logger.info("--- Time Message Conversion ---")
    stamp = Time(seconds=12, nanoseconds=345, clock_type=ClockType.ROS_TIME)
    stamp_msg = stamp.to_msg()
    logger.info(f"Time message: sec={stamp_msg.sec}, nanosec={stamp_msg.nanosec}")

    duration = Duration(seconds=1, nanoseconds=250_000_000)
    duration_msg = duration.to_msg()
    logger.info(f"Duration message: sec={duration_msg.sec}, nanosec={duration_msg.nanosec}")

    logger.info("--- Elapsed Time ---")
    start = system_clock.now()
    time.sleep(0.2)
    elapsed = system_clock.now() - start
    logger.info(f"Elapsed: {elapsed.nanoseconds / 1e9:.3f}s")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
