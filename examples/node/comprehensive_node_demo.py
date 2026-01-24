#!/usr/bin/env python3
"""Comprehensive ROS 2 node demonstration.

This example shows:
- Node creation with various parameters
- Parameter handling
- Logger usage
- Creating multiple entities (publishers, subscribers, timers, services)
- Namespace handling
"""

import rclpy
from std_msgs.msg import String, Int32
from std_srvs.srv import SetBool


def main():
    rclpy.init()
    
    # 1. Basic node creation
    print("=== Comprehensive Node Demo ===\n")
    
    print("--- Node Creation Options ---")
    
    # Simple node
    simple_node = rclpy.create_node("simple_node")
    print(f"Simple node: {simple_node.get_name()}")
    print(f"  Namespace: '{simple_node.get_namespace()}'")
    print(f"  Fully qualified: {simple_node.get_fully_qualified_name()}")
    
    simple_node.destroy_node()
    
    # Node with namespace
    ns_node = rclpy.create_node("namespaced_node", namespace="/robot")
    print(f"\nNamespaced node: {ns_node.get_name()}")
    print(f"  Namespace: '{ns_node.get_namespace()}'")
    print(f"  Fully qualified: {ns_node.get_fully_qualified_name()}")
    
    ns_node.destroy_node()
    
    # 2. Node with all features
    print("\n--- Full Featured Node ---")
    
    node = rclpy.create_node("feature_demo", namespace="/demo")
    logger = node.get_logger()
    
    logger.info(f"Node name: {node.get_name()}")
    logger.info(f"Namespace: {node.get_namespace()}")
    
    # 3. Parameters
    print("\n--- Parameters ---")
    
    # Declare parameters
    node.declare_parameter("robot_name", "R2D2")
    node.declare_parameter("max_speed", 1.5)
    node.declare_parameter("enabled", True)
    
    # Get parameters
    robot_name = node.get_parameter("robot_name")
    max_speed = node.get_parameter("max_speed")
    enabled = node.get_parameter("enabled")
    
    logger.info(f"robot_name: {robot_name.value}")
    logger.info(f"max_speed: {max_speed.value}")
    logger.info(f"enabled: {enabled.value}")
    
    # Set parameter
    node.set_parameter("max_speed", 2.0)
    logger.info(f"Updated max_speed: {node.get_parameter('max_speed').value}")
    
    # 4. Create multiple entities
    print("\n--- Creating Communication Entities ---")
    
    # Publishers
    pub_string = node.create_publisher(String, "status", 10)
    pub_int = node.create_publisher(Int32, "counter", 10)
    logger.info(f"Created publishers: status, counter")
    
    # Subscribers
    received = {'status': None, 'counter': None}
    
    def status_callback(msg):
        received['status'] = msg.data
        logger.info(f"Received status: {msg.data}")
    
    def counter_callback(msg):
        received['counter'] = msg.data
        logger.info(f"Received counter: {msg.data}")
    
    sub_status = node.create_subscription(String, "status", status_callback, 10)
    sub_counter = node.create_subscription(Int32, "counter", counter_callback, 10)
    logger.info(f"Created subscribers: status, counter")
    
    # Service
    def handle_enable(request, response):
        enabled = request.data
        response.success = True
        response.message = f"Robot {'enabled' if enabled else 'disabled'}"
        logger.info(f"Service: Robot {'enabled' if enabled else 'disabled'}")
        return response
    
    srv = node.create_service(SetBool, "enable", handle_enable)
    logger.info(f"Created service: enable")
    
    # Timer
    timer_count = {'value': 0}
    
    def timer_callback():
        timer_count['value'] += 1
        
        # Publish status
        msg = String()
        msg.data = f"Status update #{timer_count['value']}"
        pub_string.publish(msg)
        
        # Publish counter
        counter = Int32()
        counter.data = timer_count['value']
        pub_int.publish(counter)
    
    timer = node.create_timer(0.5, timer_callback)
    logger.info(f"Created timer: 0.5s period")
    
    # 5. Run for a while
    print("\n--- Running Node ---")
    logger.info("Spinning for 3 seconds...")
    
    import time
    start = time.monotonic()
    while rclpy.ok() and (time.monotonic() - start) < 3.0:
        rclpy.spin_once(node, timeout_sec=0.1)
    
    # 6. Summary
    print("\n--- Summary ---")
    logger.info(f"Timer callbacks: {timer_count['value']}")
    logger.info(f"Last received status: {received['status']}")
    logger.info(f"Last received counter: {received['counter']}")
    
    # 7. Cleanup
    print("\n--- Cleanup ---")
    timer.cancel()
    node.destroy_timer(timer)
    node.destroy_publisher(pub_string)
    node.destroy_publisher(pub_int)
    node.destroy_subscription(sub_status)
    node.destroy_subscription(sub_counter)
    node.destroy_service(srv)
    logger.info("All entities destroyed")
    
    node.destroy_node()
    rclpy.shutdown()
    
    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
