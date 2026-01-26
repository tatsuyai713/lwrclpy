#!/usr/bin/env python3
"""Simulated time with Clock override.

This example shows:
- Using simulated time for testing
- Time jump callbacks
- Controlling simulation speed
"""

import time
import rclpy
from lwrclpy.clock import Clock, ClockType, Time
from lwrclpy.duration import Duration


def main():
    rclpy.init()
    node = rclpy.create_node("sim_time_demo")
    logger = node.get_logger()
    
    logger.info("=== Simulated Time Demo ===\n")
    
    # Create ROS time clock (can be overridden)
    ros_clock = Clock(clock_type=ClockType.ROS_TIME)
    
    # System clock for comparison
    system_clock = Clock(clock_type=ClockType.SYSTEM_TIME)
    
    # 1. Without override - uses system time
    logger.info("--- Without time override ---")
    logger.info(f"ROS time active: {ros_clock.ros_time_is_active}")
    
    sys_now = system_clock.now()
    ros_now = ros_clock.now()
    
    logger.info(f"System time: {sys_now}")
    logger.info(f"ROS time: {ros_now}")
    logger.info("(They should be similar when override is not active)")
    logger.info("")
    
    # 2. Enable time override (simulation mode)
    logger.info("--- With time override (simulation) ---")
    
    # Start simulation at t=0
    sim_start = Time(seconds=0, nanoseconds=0, clock_type=ClockType.ROS_TIME)
    ros_clock.set_ros_time_override(sim_start)
    
    logger.info(f"ROS time active: {ros_clock.ros_time_is_active}")
    logger.info(f"Simulated time: {ros_clock.now()}")
    logger.info("")
    
    # 3. Advance simulated time
    logger.info("--- Advancing simulated time ---")
    
    sim_times = [0, 1, 5, 10, 60, 3600]  # seconds
    
    for sim_sec in sim_times:
        new_time = Time(seconds=sim_sec, nanoseconds=0, clock_type=ClockType.ROS_TIME)
        ros_clock.set_ros_time_override(new_time)
        
        logger.info(f"Sim time set to {sim_sec}s -> ros_clock.now() = {ros_clock.now()}")
    
    logger.info("")
    
    # 4. Simulated time progression at different speeds
    logger.info("--- Time progression at 10x speed ---")
    
    sim_speed = 10.0
    real_duration = 1.0  # 1 second of real time
    
    base_sim_time = 0.0
    real_start = time.monotonic()
    
    logger.info(f"Running for {real_duration}s real time at {sim_speed}x speed")
    logger.info(f"Expected simulated duration: {real_duration * sim_speed}s")
    
    while (time.monotonic() - real_start) < real_duration:
        # Calculate simulated time based on real elapsed time
        real_elapsed = time.monotonic() - real_start
        sim_time_sec = base_sim_time + (real_elapsed * sim_speed)
        
        new_time = Time(seconds=int(sim_time_sec), 
                       nanoseconds=int((sim_time_sec % 1) * 1e9),
                       clock_type=ClockType.ROS_TIME)
        ros_clock.set_ros_time_override(new_time)
        
        time.sleep(0.1)
    
    final_sim = ros_clock.now()
    real_elapsed = time.monotonic() - real_start
    
    logger.info(f"Real elapsed: {real_elapsed:.2f}s")
    logger.info(f"Final sim time: {final_sim}")
    logger.info("")
    
    # 5. Pause simulation (freeze time)
    logger.info("--- Pausing simulation ---")
    
    frozen_time = Time(seconds=100, nanoseconds=0, clock_type=ClockType.ROS_TIME)
    ros_clock.set_ros_time_override(frozen_time)
    
    logger.info(f"Time frozen at: {ros_clock.now()}")
    time.sleep(0.5)
    logger.info(f"After 0.5s real time: {ros_clock.now()}")
    logger.info("(Simulated time did not advance)")
    logger.info("")
    
    # 6. Resume and clear override
    logger.info("--- Clearing override (back to system time) ---")
    
    ros_clock.clear_ros_time_override()
    
    logger.info(f"ROS time active: {ros_clock.ros_time_is_active}")
    logger.info(f"ROS time now: {ros_clock.now()}")
    logger.info(f"System time: {system_clock.now()}")
    logger.info("(Should be similar again)")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
