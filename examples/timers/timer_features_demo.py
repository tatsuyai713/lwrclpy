#!/usr/bin/env python3
"""Enhanced timer demonstration with new features.

This example shows:
- Timer drift compensation
- is_ready() for manual checking
- time_since_last_call() for timing info
- call_count tracking
- timer_period_ns property
"""

import time
import rclpy
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("timer_features_demo")
    logger = node.get_logger()
    
    logger.info("=== Enhanced Timer Features Demo ===\n")
    
    # Track execution times for drift analysis
    execution_times = []
    expected_period = 0.1  # 100ms
    
    def timer_callback():
        now = time.monotonic()
        execution_times.append(now)
        
        # Access timer properties (timer variable captured from outer scope)
        call_count = timer.call_count
        time_since_last = timer.time_since_last_call()
        period_ns = timer.timer_period_ns
        
        logger.info(f"Call #{call_count}: "
                   f"time_since_last={time_since_last:.4f}s, "
                   f"period={period_ns/1e9:.3f}s")
        
        # Simulate some work (varying)
        work_time = (call_count % 3) * 0.01  # 0, 10, 20ms
        time.sleep(work_time)
    
    # Create timer with 100ms period
    logger.info("Creating timer with 100ms period")
    timer = node.create_timer(expected_period, timer_callback)
    
    logger.info(f"Timer period: {timer.timer_period_ns / 1e9:.3f} seconds")
    logger.info(f"Initial call count: {timer.call_count}")
    logger.info("")
    
    # Run for a while
    logger.info("--- Running timer for 10 iterations ---\n")
    start_time = time.monotonic()
    
    while rclpy.ok() and timer.call_count < 10:
        rclpy.spin_once(node, timeout_sec=0.01)
    
    elapsed = time.monotonic() - start_time
    
    # Analyze timing
    logger.info("\n--- Timing Analysis ---")
    logger.info(f"Total elapsed time: {elapsed:.3f}s")
    logger.info(f"Expected time: {expected_period * 10:.3f}s")
    logger.info(f"Total calls: {timer.call_count}")
    
    if len(execution_times) >= 2:
        intervals = []
        for i in range(1, len(execution_times)):
            interval = execution_times[i] - execution_times[i-1]
            intervals.append(interval)
        
        avg_interval = sum(intervals) / len(intervals)
        max_interval = max(intervals)
        min_interval = min(intervals)
        
        logger.info(f"Average interval: {avg_interval:.4f}s (expected: {expected_period:.4f}s)")
        logger.info(f"Drift from expected: {(avg_interval - expected_period) * 1000:.2f}ms")
        logger.info(f"Min interval: {min_interval:.4f}s")
        logger.info(f"Max interval: {max_interval:.4f}s")
    
    # Demonstrate is_ready()
    logger.info("\n--- is_ready() Demo ---")
    timer.cancel()
    
    # Create a new timer and check readiness
    check_timer = node.create_timer(0.5, lambda: None)
    
    logger.info(f"Immediately after creation, is_ready(): {check_timer.is_ready()}")
    
    time.sleep(0.6)
    logger.info(f"After 600ms wait, is_ready(): {check_timer.is_ready()}")
    
    check_timer.cancel()
    
    # Demonstrate oneshot behavior
    logger.info("\n--- Oneshot Timer Demo ---")
    oneshot_called = {'count': 0}
    
    def oneshot_callback():
        oneshot_called['count'] += 1
        logger.info(f"Oneshot called! (count: {oneshot_called['count']})")
        oneshot_timer.cancel()  # Cancel after first call
    
    oneshot_timer = node.create_timer(0.2, oneshot_callback)
    
    # Wait for it to fire
    wait_start = time.monotonic()
    while rclpy.ok() and oneshot_called['count'] == 0 and (time.monotonic() - wait_start) < 1.0:
        rclpy.spin_once(node, timeout_sec=0.05)
    
    logger.info(f"Oneshot timer fired {oneshot_called['count']} time(s)")
    
    # Give time to confirm it doesn't fire again
    time.sleep(0.5)
    while rclpy.ok():
        if not rclpy.spin_once(node, timeout_sec=0.1):
            break
        if oneshot_called['count'] > 1:
            break
    
    logger.info(f"After additional wait: {oneshot_called['count']} call(s) (should still be 1)")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
