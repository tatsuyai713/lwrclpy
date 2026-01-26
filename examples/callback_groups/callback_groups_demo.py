#!/usr/bin/env python3
"""Demonstration of callback groups.

This example shows:
- MutuallyExclusiveCallbackGroup (only one callback at a time)
- ReentrantCallbackGroup (callbacks can run concurrently)
- Using callback groups with timers and subscriptions
"""

import time
import threading
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("callback_groups_demo")
    logger = node.get_logger()
    
    logger.info("=== Callback Groups Demo ===")
    logger.info("Demonstrating mutual exclusion vs reentrant callbacks\n")
    
    # Create callback groups
    mutex_group = MutuallyExclusiveCallbackGroup()
    reentrant_group = ReentrantCallbackGroup()
    
    # Track concurrent executions
    mutex_executions = []
    reentrant_executions = []
    lock = threading.Lock()
    
    def make_callback(name, execution_list):
        def callback():
            thread_id = threading.current_thread().name
            start = time.monotonic()
            
            with lock:
                execution_list.append((name, thread_id, "start", start))
            
            logger.info(f"[{name}] Started on thread {thread_id}")
            
            # Simulate work
            time.sleep(0.3)
            
            end = time.monotonic()
            with lock:
                execution_list.append((name, thread_id, "end", end))
            
            logger.info(f"[{name}] Finished on thread {thread_id}")
        
        return callback
    
    # Create timers with different callback groups
    logger.info("--- Setting up callbacks ---")
    logger.info("Mutex group: timer_mutex_1, timer_mutex_2 (should NOT overlap)")
    logger.info("Reentrant group: timer_reentrant_1, timer_reentrant_2 (CAN overlap)\n")
    
    # Note: In lwrclpy, callback_group parameter is accepted but the actual
    # mutual exclusion is handled at the application level in real rclpy.
    # This example demonstrates the concept.
    
    timer1 = node.create_timer(0.2, make_callback("timer_mutex_1", mutex_executions),
                                callback_group=mutex_group)
    timer2 = node.create_timer(0.2, make_callback("timer_mutex_2", mutex_executions),
                                callback_group=mutex_group)
    timer3 = node.create_timer(0.2, make_callback("timer_reentrant_1", reentrant_executions),
                                callback_group=reentrant_group)
    timer4 = node.create_timer(0.2, make_callback("timer_reentrant_2", reentrant_executions),
                                callback_group=reentrant_group)
    
    # Run for a short time
    logger.info("--- Running callbacks for 2 seconds ---\n")
    
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    
    start_time = time.monotonic()
    try:
        while rclpy.ok() and (time.monotonic() - start_time) < 2.0:
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    
    # Cancel timers
    timer1.cancel()
    timer2.cancel()
    timer3.cancel()
    timer4.cancel()
    
    # Analyze results
    logger.info("\n--- Analysis ---")
    logger.info(f"Mutex group callback events: {len(mutex_executions)}")
    logger.info(f"Reentrant group callback events: {len(reentrant_executions)}")
    
    # Check for overlapping executions in mutex group
    logger.info("\nMutex Group Behavior:")
    logger.info("  MutuallyExclusiveCallbackGroup ensures only one callback")
    logger.info("  from the group executes at a time (serialized execution)")
    
    logger.info("\nReentrant Group Behavior:")
    logger.info("  ReentrantCallbackGroup allows callbacks to run concurrently")
    logger.info("  Multiple callbacks can execute simultaneously")
    
    logger.info("\n=== Demo Complete ===")
    
    executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
