#!/usr/bin/env python3
"""Advanced guard condition demonstration.

This example shows:
- Using guard conditions for thread signaling
- Multiple guard conditions
- Guard condition with external trigger
- Coordinating between threads using guard conditions
"""

import threading
import time
import rclpy
from rclpy.executors import SingleThreadedExecutor


def main():
    rclpy.init()
    node = rclpy.create_node("guard_condition_advanced_demo")
    logger = node.get_logger()
    
    logger.info("=== Advanced Guard Condition Demo ===\n")
    
    # Track events
    events = []
    
    # 1. Basic guard condition
    logger.info("--- Creating Guard Conditions ---")
    
    def gc1_callback():
        events.append(("gc1", time.monotonic()))
        logger.info("Guard condition 1 triggered!")
    
    def gc2_callback():
        events.append(("gc2", time.monotonic()))
        logger.info("Guard condition 2 triggered!")
    
    gc1 = node.create_guard_condition(gc1_callback)
    gc2 = node.create_guard_condition(gc2_callback)
    
    logger.info("Created two guard conditions")
    
    # 2. External thread that triggers guard conditions
    logger.info("\n--- Starting External Trigger Thread ---")
    
    stop_event = threading.Event()
    
    def external_trigger_thread():
        """Simulates external event source triggering guard conditions."""
        trigger_count = 0
        while not stop_event.is_set() and trigger_count < 6:
            time.sleep(0.5)
            
            # Alternate between guard conditions
            if trigger_count % 2 == 0:
                logger.info("External thread: triggering gc1")
                gc1.trigger()
            else:
                logger.info("External thread: triggering gc2")
                gc2.trigger()
            
            trigger_count += 1
        
        logger.info("External trigger thread finished")
    
    trigger_thread = threading.Thread(target=external_trigger_thread, name="TriggerThread")
    trigger_thread.start()
    
    # 3. Process events with executor
    logger.info("Processing events with executor...\n")
    
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    
    start_time = time.monotonic()
    while rclpy.ok() and (time.monotonic() - start_time) < 4.0:
        executor.spin_once(timeout_sec=0.1)
    
    # Signal thread to stop and wait
    stop_event.set()
    trigger_thread.join()
    
    # 4. Summary
    logger.info("\n--- Event Summary ---")
    logger.info(f"Total events: {len(events)}")
    
    gc1_count = sum(1 for e in events if e[0] == "gc1")
    gc2_count = sum(1 for e in events if e[0] == "gc2")
    
    logger.info(f"  gc1 triggered: {gc1_count} times")
    logger.info(f"  gc2 triggered: {gc2_count} times")
    
    # 5. Demonstrate guard condition for shutdown signal
    logger.info("\n--- Guard Condition for Shutdown ---")
    
    shutdown_received = threading.Event()
    
    def shutdown_callback():
        logger.info("Shutdown guard condition triggered!")
        shutdown_received.set()
    
    gc_shutdown = node.create_guard_condition(shutdown_callback)
    
    # Simulate external shutdown signal
    def delayed_shutdown():
        time.sleep(0.5)
        logger.info("Sending shutdown signal via guard condition...")
        gc_shutdown.trigger()
    
    shutdown_thread = threading.Thread(target=delayed_shutdown)
    shutdown_thread.start()
    
    # Wait for shutdown signal
    while rclpy.ok() and not shutdown_received.is_set():
        executor.spin_once(timeout_sec=0.1)
    
    shutdown_thread.join()
    
    logger.info("\n=== Demo Complete ===")
    
    executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
