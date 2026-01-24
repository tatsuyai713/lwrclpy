#!/usr/bin/env python3
"""Demonstration of Clock, Time, and Duration classes.

This example shows:
- Different clock types (SYSTEM_TIME, STEADY_TIME, ROS_TIME)
- Time and Duration arithmetic
- Simulated time override for testing
- Time comparisons
"""

import rclpy
from lwrclpy.clock import Clock, ClockType, Time, Duration


def main():
    rclpy.init()
    node = rclpy.create_node("clock_demo")
    logger = node.get_logger()
    
    logger.info("=== Clock, Time, and Duration Demo ===\n")
    
    # 1. System Clock (wall clock)
    logger.info("--- System Clock ---")
    system_clock = Clock(clock_type=ClockType.SYSTEM_TIME)
    now = system_clock.now()
    sec, nsec = now.seconds_nanoseconds
    logger.info(f"Current system time: {sec}.{nsec:09d} seconds")
    logger.info(f"Nanoseconds: {now.nanoseconds}")
    
    # 2. Steady Clock (monotonic)
    logger.info("\n--- Steady Clock ---")
    steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
    steady_now = steady_clock.now()
    logger.info(f"Steady clock: {steady_now}")
    
    # 3. Node's default clock
    logger.info("\n--- Node Clock ---")
    node_clock = node.get_clock()
    node_now = node_clock.now()
    logger.info(f"Node clock: {node_now}")
    
    # 4. Time arithmetic
    logger.info("\n--- Time Arithmetic ---")
    t1 = Time(seconds=10, nanoseconds=500_000_000)  # 10.5 seconds
    t2 = Time(seconds=5, nanoseconds=200_000_000)   # 5.2 seconds
    
    logger.info(f"t1 = {t1}")
    logger.info(f"t2 = {t2}")
    
    # Time difference -> Duration
    diff = t1 - t2
    logger.info(f"t1 - t2 = {diff} ({diff.nanoseconds / 1e9:.1f} seconds)")
    
    # Time + Duration
    d = Duration(seconds=2, nanoseconds=0)
    t3 = t1 + d
    logger.info(f"t1 + 2s = {t3}")
    
    # 5. Time comparisons
    logger.info("\n--- Time Comparisons ---")
    logger.info(f"t1 > t2: {t1 > t2}")
    logger.info(f"t1 == t2: {t1 == t2}")
    logger.info(f"t1 >= t1: {t1 >= t1}")
    
    # 6. Duration arithmetic
    logger.info("\n--- Duration Arithmetic ---")
    d1 = Duration(seconds=5, nanoseconds=0)
    d2 = Duration(seconds=3, nanoseconds=500_000_000)
    
    logger.info(f"d1 = {d1}")
    logger.info(f"d2 = {d2}")
    logger.info(f"d1 + d2 = {d1 + d2}")
    logger.info(f"d1 - d2 = {d1 - d2}")
    logger.info(f"d1 * 2 = {d1 * 2}")
    logger.info(f"d1 / 2 = {d1 / 2}")
    logger.info(f"d1 / d2 = {d1 / d2:.2f}")
    
    # 7. Simulated time (ROS Time override)
    logger.info("\n--- Simulated Time (ROS Time) ---")
    ros_clock = Clock(clock_type=ClockType.ROS_TIME)
    
    logger.info(f"ROS time active: {ros_clock.ros_time_is_active}")
    
    # Set simulated time
    sim_time = Time(seconds=1000, nanoseconds=0, clock_type=ClockType.ROS_TIME)
    ros_clock.set_ros_time_override(sim_time)
    
    logger.info(f"ROS time active after override: {ros_clock.ros_time_is_active}")
    logger.info(f"Simulated time: {ros_clock.now()}")
    
    # Advance simulated time
    new_sim_time = Time(seconds=1005, nanoseconds=0, clock_type=ClockType.ROS_TIME)
    ros_clock.set_ros_time_override(new_sim_time)
    logger.info(f"Advanced simulated time: {ros_clock.now()}")
    
    # Clear override
    ros_clock.clear_ros_time_override()
    logger.info(f"After clearing override, ROS time active: {ros_clock.ros_time_is_active}")
    
    # 8. Sleep demonstration
    logger.info("\n--- Sleep Demo ---")
    logger.info("Sleeping for 0.5 seconds using sleep_for()...")
    start = system_clock.now()
    system_clock.sleep_for(Duration(seconds=0, nanoseconds=500_000_000))
    end = system_clock.now()
    elapsed = end - start
    logger.info(f"Actual sleep duration: {elapsed.nanoseconds / 1e9:.3f} seconds")
    
    # 9. Converting to/from ROS messages
    logger.info("\n--- Message Conversion ---")
    time_obj = Time(seconds=123, nanoseconds=456789)
    time_msg = time_obj.to_msg()
    if time_msg:
        logger.info(f"Time to message: sec={time_msg.sec()}, nanosec={time_msg.nanosec()}")
    
    duration_obj = Duration(seconds=10, nanoseconds=500000000)
    duration_msg = duration_obj.to_msg()
    if duration_msg:
        logger.info(f"Duration to message: sec={duration_msg.sec()}, nanosec={duration_msg.nanosec()}")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
