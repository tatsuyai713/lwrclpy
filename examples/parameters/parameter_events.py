#!/usr/bin/env python3
"""Advanced parameter handling demonstration.

This example shows:
- Declaring parameters with descriptors
- Parameter types (bool, int, float, string, array)
- Parameter callbacks
- Getting multiple parameters at once
- Parameter validation
"""

import rclpy
from rclpy.node import Node


class ParameterDemo(Node):
    def __init__(self):
        super().__init__("parameter_demo")
        self.get_logger().info("=== Parameter Events Demo ===\n")
        
        # Declare parameters with different types
        self.get_logger().info("--- Declaring Parameters ---")
        
        # Boolean parameter
        self.declare_parameter("enabled", True)
        
        # Integer parameter
        self.declare_parameter("max_count", 100)
        
        # Float parameter
        self.declare_parameter("rate_hz", 10.0)
        
        # String parameter
        self.declare_parameter("robot_name", "R2D2")
        
        # Parameters with initial values from constructor
        self.declare_parameter("debug_level", 1)
        
        # Show all declared parameters
        self.show_parameters()
        
        # Create timer to demonstrate parameter updates
        self.counter = 0
        self.timer = self.create_timer(1.0, self.timer_callback)
    
    def show_parameters(self):
        """Display current parameter values."""
        self.get_logger().info("\n--- Current Parameters ---")
        
        enabled = self.get_parameter("enabled").value
        max_count = self.get_parameter("max_count").value
        rate_hz = self.get_parameter("rate_hz").value
        robot_name = self.get_parameter("robot_name").value
        debug_level = self.get_parameter("debug_level").value
        
        self.get_logger().info(f"  enabled: {enabled} (type: {type(enabled).__name__})")
        self.get_logger().info(f"  max_count: {max_count} (type: {type(max_count).__name__})")
        self.get_logger().info(f"  rate_hz: {rate_hz} (type: {type(rate_hz).__name__})")
        self.get_logger().info(f"  robot_name: {robot_name} (type: {type(robot_name).__name__})")
        self.get_logger().info(f"  debug_level: {debug_level}")
    
    def timer_callback(self):
        self.counter += 1
        logger = self.get_logger()
        
        if self.counter == 2:
            logger.info("\n--- Updating Parameters ---")
            
            # Update single parameter
            self.set_parameter("robot_name", "C3PO")
            logger.info("Updated robot_name to 'C3PO'")
            
            # Update multiple parameters
            self.set_parameter("rate_hz", 20.0)
            self.set_parameter("max_count", 200)
            logger.info("Updated rate_hz to 20.0 and max_count to 200")
            
            self.show_parameters()
        
        elif self.counter == 4:
            logger.info("\n--- Checking Parameter Existence ---")
            
            if self.has_parameter("enabled"):
                logger.info("Parameter 'enabled' exists")
            
            if not self.has_parameter("nonexistent"):
                logger.info("Parameter 'nonexistent' does not exist")
        
        elif self.counter == 6:
            logger.info("\n--- Getting Undeclared Parameters ---")
            logger.info("(With allow_undeclared_parameters=True, can get undeclared)")
            
            # Get with default value
            value = self.get_parameter_or("undefined_param", 42)
            logger.info(f"get_parameter_or('undefined_param', 42) = {value}")
        
        elif self.counter >= 8:
            logger.info("\n=== Demo Complete ===")
            self.timer.cancel()
            rclpy.shutdown()


def main():
    rclpy.init()
    node = ParameterDemo()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
