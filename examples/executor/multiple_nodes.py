#!/usr/bin/env python3
"""Multiple nodes in one process.

This example shows:
- Running multiple nodes in a single process
- Using executor with multiple nodes
- Inter-node communication
"""

import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String, Int32


def main():
    rclpy.init()
    
    # Create multiple nodes
    producer_node = rclpy.create_node("producer")
    processor_node = rclpy.create_node("processor")
    monitor_node = rclpy.create_node("monitor")
    
    producer_logger = producer_node.get_logger()
    processor_logger = processor_node.get_logger()
    monitor_logger = monitor_node.get_logger()
    
    producer_logger.info("=== Multiple Nodes Demo ===\n")
    
    # State
    processed_count = {"value": 0}
    
    # Producer node: generates data
    pub_raw = producer_node.create_publisher(Int32, "/raw_data", 10)
    counter = {"value": 0}
    
    def produce():
        counter["value"] += 1
        msg = Int32()
        msg.data = counter["value"]
        pub_raw.publish(msg)
        producer_logger.info(f"[Producer] Generated: {counter['value']}")
    
    producer_timer = producer_node.create_timer(0.5, produce)
    
    # Processor node: processes data
    pub_processed = processor_node.create_publisher(String, "/processed_data", 10)
    
    def process(msg):
        value = msg.data
        result = f"processed_{value}_x2={value*2}"
        
        out = String()
        out.data = result
        pub_processed.publish(out)
        
        processed_count["value"] += 1
        processor_logger.info(f"[Processor] {value} -> {result}")
    
    sub_raw = processor_node.create_subscription(Int32, "/raw_data", process, 10)
    
    # Monitor node: observes everything
    def monitor_raw(msg):
        monitor_logger.debug(f"[Monitor] Saw raw: {msg.data}")
    
    def monitor_processed(msg):
        monitor_logger.info(f"[Monitor] Saw processed: {msg.data}")
    
    sub_monitor_raw = monitor_node.create_subscription(Int32, "/raw_data", monitor_raw, 10)
    sub_monitor_processed = monitor_node.create_subscription(String, "/processed_data", monitor_processed, 10)
    
    # Status timer on monitor
    def status():
        monitor_logger.info(f"[Monitor] Status: {processed_count['value']} items processed")
    
    monitor_timer = monitor_node.create_timer(2.0, status)
    
    # Create executor and add all nodes
    executor = SingleThreadedExecutor()
    executor.add_node(producer_node)
    executor.add_node(processor_node)
    executor.add_node(monitor_node)
    
    producer_logger.info("Created 3 nodes: producer, processor, monitor")
    producer_logger.info("Pipeline: producer -> /raw_data -> processor -> /processed_data -> monitor")
    producer_logger.info("Running for 5 seconds...\n")
    
    import time
    start = time.monotonic()
    
    try:
        while rclpy.ok() and (time.monotonic() - start) < 5.0:
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    
    # Summary
    producer_logger.info(f"\n--- Summary ---")
    producer_logger.info(f"Items produced: {counter['value']}")
    producer_logger.info(f"Items processed: {processed_count['value']}")
    
    producer_logger.info("\n=== Demo Complete ===")
    
    # Cleanup
    producer_timer.cancel()
    monitor_timer.cancel()
    executor.shutdown()
    producer_node.destroy_node()
    processor_node.destroy_node()
    monitor_node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
