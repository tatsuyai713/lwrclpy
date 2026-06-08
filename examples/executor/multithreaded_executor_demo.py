#!/usr/bin/env python3
"""Demonstration of MultiThreadedExecutor and thread safety.

This example shows:
- Using MultiThreadedExecutor with multiple nodes
- Thread-safe callback execution
- Using wake() to interrupt executor
- Graceful shutdown with timeout
"""

import time
import threading
import sys
import rclpy
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import Int32


def main():
    rclpy.init()
    
    # Create multiple nodes
    node1 = rclpy.create_node("publisher_node")
    node2 = rclpy.create_node("subscriber_node")
    node3 = rclpy.create_node("processor_node")
    
    logger = node1.get_logger()
    logger.info("=== MultiThreadedExecutor Demo ===\n")
    
    # Shared state with thread-safe access
    message_count = {'received': 0, 'processed': 0}
    count_lock = threading.Lock()
    done = threading.Event()
    
    # Create publisher
    pub = node1.create_publisher(Int32, "/counter", 10)
    
    # Create subscriber on node2
    def on_receive(msg):
        with count_lock:
            message_count['received'] += 1
            count = message_count['received']
        thread_name = threading.current_thread().name
        node2.get_logger().info(f"[Thread: {thread_name}] Received: {msg.data}")
        if count >= 5:
            done.set()
            executor.wake()
    
    sub = node2.create_subscription(Int32, "/counter", on_receive, 10)
    
    # Create processor timer on node3
    def process_data():
        with count_lock:
            message_count['processed'] += 1
            proc_count = message_count['processed']
        thread_name = threading.current_thread().name
        # Simulate some processing work
        time.sleep(0.05)
        node3.get_logger().info(f"[Thread: {thread_name}] Processed batch {proc_count}")
    
    timer = node3.create_timer(0.2, process_data)
    
    # Create MultiThreadedExecutor
    logger.info("Creating MultiThreadedExecutor with 4 threads")
    executor = MultiThreadedExecutor(num_threads=4)
    
    # Add all nodes
    executor.add_node(node1)
    executor.add_node(node2)
    executor.add_node(node3)
    
    logger.info(f"Nodes in executor: {len(executor.get_nodes())}")
    for node in executor.get_nodes():
        logger.info(f"  - {node.get_name()}")
    logger.info("")
    
    counter = {'value': 0}

    def publish_once():
        if done.is_set():
            return
        with count_lock:
            value = counter['value']
            counter['value'] += 1
        if value < 10:
            msg = Int32()
            msg.data = value
            pub.publish(msg)
            logger.info(f"Published: {value}")
        else:
            logger.info("Publisher done, waking executor...")
            done.set()
            executor.wake()

    publish_timer = node1.create_timer(0.15, publish_once)
    
    # Spin in another thread
    logger.info("Starting executor spin...")
    executor_thread = threading.Thread(
        target=lambda: executor.spin(),
        name="ExecutorThread",
        daemon=True,
    )
    executor_thread.start()
    
    # Wait until subscriber progress is observed.  Keep this bounded so the
    # example is deterministic in slow CI runners.
    deadline = time.monotonic() + 12.0
    while rclpy.ok() and not done.is_set() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not done.is_set():
        logger.warning("Timed out waiting for subscriber progress; continuing shutdown")
    
    # Give some time for remaining callbacks
    time.sleep(0.5)
    
    # Shutdown executor gracefully
    logger.info("\nShutting down executor...")
    success = executor.shutdown(timeout_sec=2.0)
    logger.info(f"Shutdown completed: {success}")
    
    executor_thread.join(timeout=2.0)
    if executor_thread.is_alive():
        logger.warning("Executor thread did not finish before timeout")
    
    # Report stats
    with count_lock:
        logger.info(f"\n--- Statistics ---")
        logger.info(f"Messages received: {message_count['received']}")
        logger.info(f"Processing batches: {message_count['processed']}")
    
    logger.info("\n=== Demo Complete ===")
    
    # Cleanup
    node1.destroy_timer(publish_timer)
    node1.destroy_node()
    node2.destroy_node()
    node3.destroy_node()
    rclpy.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
