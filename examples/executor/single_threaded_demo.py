#!/usr/bin/env python3
"""Single-threaded executor basics.

This example shows:
- SingleThreadedExecutor usage
- spin_once vs spin
- Processing callbacks manually
- Timeout handling
"""

import time
import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String


def main():
    rclpy.init()
    
    node = rclpy.create_node("single_threaded_demo")
    logger = node.get_logger()
    
    logger.info("=== SingleThreadedExecutor Demo ===\n")
    
    # Track events
    events = []
    
    # Create publisher and subscriber
    pub = node.create_publisher(String, "/executor_demo", 10)
    
    def callback(msg):
        events.append(("sub", msg.data, time.monotonic()))
        logger.info(f"[Subscriber] Received: {msg.data}")
    
    sub = node.create_subscription(String, "/executor_demo", callback, 10)
    
    # Create timer
    timer_count = {"value": 0}
    
    def timer_callback():
        timer_count["value"] += 1
        events.append(("timer", timer_count["value"], time.monotonic()))
        logger.info(f"[Timer] Tick {timer_count['value']}")
        
        # Publish message
        msg = String()
        msg.data = f"Message {timer_count['value']}"
        pub.publish(msg)
    
    timer = node.create_timer(0.5, timer_callback)
    
    # Create executor
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    
    logger.info("Executor created with one node")
    logger.info("Processing callbacks for 3 seconds...\n")
    
    # Method 1: spin_once in a loop
    logger.info("--- Using spin_once in loop ---")
    start = time.monotonic()
    
    while rclpy.ok() and (time.monotonic() - start) < 1.5:
        # Process one callback with timeout
        executor.spin_once(timeout_sec=0.1)
    
    logger.info(f"Processed {len(events)} events in 1.5 seconds\n")
    
    # Method 2: spin_once with different timeouts
    logger.info("--- spin_once with short timeout ---")
    
    short_timeout_count = 0
    short_start = time.monotonic()
    
    while (time.monotonic() - short_start) < 0.5:
        # Very short timeout - returns quickly if no work
        had_work = executor.spin_once(timeout_sec=0.01)
        short_timeout_count += 1
    
    logger.info(f"spin_once called {short_timeout_count} times in 0.5s\n")
    
    # Method 3: Processing until condition
    logger.info("--- Processing until condition ---")
    
    target_count = timer_count["value"] + 3
    logger.info(f"Waiting for timer count to reach {target_count}...")
    
    while rclpy.ok() and timer_count["value"] < target_count:
        executor.spin_once(timeout_sec=0.1)
    
    logger.info(f"Timer count reached {timer_count['value']}\n")
    
    # Summary
    logger.info("--- Event Summary ---")
    timer_events = [e for e in events if e[0] == "timer"]
    sub_events = [e for e in events if e[0] == "sub"]
    
    logger.info(f"Timer callbacks: {len(timer_events)}")
    logger.info(f"Subscriber callbacks: {len(sub_events)}")
    
    if len(timer_events) >= 2:
        intervals = []
        for i in range(1, len(timer_events)):
            intervals.append(timer_events[i][2] - timer_events[i-1][2])
        avg = sum(intervals) / len(intervals)
        logger.info(f"Average timer interval: {avg:.3f}s (expected: 0.5s)")
    
    logger.info("\n=== Demo Complete ===")
    
    timer.cancel()
    executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
