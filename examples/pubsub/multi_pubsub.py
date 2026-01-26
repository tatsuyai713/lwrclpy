#!/usr/bin/env python3
"""Multiple publishers and subscribers in one node.

This example shows:
- Creating multiple pub/sub on one node
- Topic remapping concepts
- Organizing communication within a node
"""

import rclpy
from std_msgs.msg import String, Int32, Float32


def main():
    rclpy.init()
    node = rclpy.create_node("multi_pubsub_node")
    logger = node.get_logger()
    
    logger.info("=== Multi Pub/Sub Demo ===\n")
    
    # Create multiple publishers
    pub_status = node.create_publisher(String, "/robot/status", 10)
    pub_battery = node.create_publisher(Float32, "/robot/battery", 10)
    pub_speed = node.create_publisher(Float32, "/robot/speed", 10)
    pub_errors = node.create_publisher(Int32, "/robot/error_count", 10)
    
    # State
    state = {
        "battery": 100.0,
        "speed": 0.0,
        "errors": 0,
        "status": "idle",
        "tick": 0
    }
    
    # Create subscribers (self-loopback for demo)
    def on_status(msg):
        logger.debug(f"Status update: {msg.data}")
    
    def on_battery(msg):
        if msg.data < 20.0:
            logger.warn(f"Low battery: {msg.data:.1f}%")
    
    sub_status = node.create_subscription(String, "/robot/status", on_status, 10)
    sub_battery = node.create_subscription(Float32, "/robot/battery", on_battery, 10)
    
    def timer_callback():
        state["tick"] += 1
        
        # Update state
        state["battery"] -= 0.5  # Drain battery
        state["speed"] = 1.0 + (state["tick"] % 10) * 0.1
        
        if state["tick"] % 10 == 0:
            state["errors"] += 1
        
        if state["battery"] > 50:
            state["status"] = "running"
        elif state["battery"] > 20:
            state["status"] = "low_battery"
        else:
            state["status"] = "critical"
        
        # Publish all topics
        status_msg = String()
        status_msg.data = state["status"]
        pub_status.publish(status_msg)
        
        battery_msg = Float32()
        battery_msg.data = state["battery"]
        pub_battery.publish(battery_msg)
        
        speed_msg = Float32()
        speed_msg.data = state["speed"]
        pub_speed.publish(speed_msg)
        
        error_msg = Int32()
        error_msg.data = state["errors"]
        pub_errors.publish(error_msg)
        
        logger.info(f"[tick {state['tick']}] status={state['status']}, "
                   f"battery={state['battery']:.1f}%, "
                   f"speed={state['speed']:.1f}, errors={state['errors']}")
        
        if state["battery"] <= 0:
            logger.error("Battery depleted! Shutting down...")
            timer.cancel()
            rclpy.shutdown()
    
    timer = node.create_timer(0.5, timer_callback)
    
    logger.info("Publishing on multiple topics:")
    logger.info("  /robot/status (String)")
    logger.info("  /robot/battery (Float32)")
    logger.info("  /robot/speed (Float32)")
    logger.info("  /robot/error_count (Int32)")
    logger.info("\nPress Ctrl+C to stop\n")
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        logger.info("\nStopping...")
    finally:
        timer.cancel()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
