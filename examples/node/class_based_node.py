#!/usr/bin/env python3
"""Class-based node pattern (recommended for larger projects).

This example shows:
- Node as a class
- Proper initialization and cleanup
- Organizing callbacks as methods
- Using instance variables for state
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32
from std_srvs.srv import SetBool


class RobotController(Node):
    """Example of a class-based ROS 2 node."""
    
    def __init__(self):
        super().__init__("robot_controller")
        
        self.get_logger().info("=== Class-based Node Demo ===\n")
        
        # Node parameters
        self.declare_parameter("robot_name", "Robot1")
        self.declare_parameter("update_rate", 2.0)
        
        self.robot_name = self.get_parameter("robot_name").value
        self.update_rate = self.get_parameter("update_rate").value
        
        # State variables
        self.enabled = False
        self.command_count = 0
        self.last_command = "none"
        
        # Publishers
        self.status_pub = self.create_publisher(String, "~/status", 10)
        self.command_count_pub = self.create_publisher(Int32, "~/command_count", 10)
        
        # Subscribers
        self.command_sub = self.create_subscription(
            String, "~/command", self.command_callback, 10)
        
        # Services
        self.enable_srv = self.create_service(
            SetBool, "~/enable", self.enable_callback)
        
        # Timer
        self.timer = self.create_timer(1.0 / self.update_rate, self.timer_callback)
        
        self.get_logger().info(f"Robot '{self.robot_name}' initialized")
        self.get_logger().info(f"Update rate: {self.update_rate} Hz")
        self.get_logger().info("Topics:")
        self.get_logger().info(f"  Pub: {self.get_name()}/status")
        self.get_logger().info(f"  Pub: {self.get_name()}/command_count")
        self.get_logger().info(f"  Sub: {self.get_name()}/command")
        self.get_logger().info(f"  Srv: {self.get_name()}/enable")
        self.get_logger().info("")
    
    def command_callback(self, msg):
        """Handle incoming commands."""
        self.last_command = msg.data
        self.command_count += 1
        
        if not self.enabled:
            self.get_logger().warn(f"Received command '{msg.data}' but robot is disabled")
            return
        
        self.get_logger().info(f"Executing command: {msg.data}")
        # In a real robot, execute the command here
    
    def enable_callback(self, request, response):
        """Handle enable/disable service."""
        self.enabled = request.data
        
        if self.enabled:
            response.success = True
            response.message = f"{self.robot_name} enabled"
            self.get_logger().info("Robot ENABLED")
        else:
            response.success = True
            response.message = f"{self.robot_name} disabled"
            self.get_logger().info("Robot DISABLED")
        
        return response
    
    def timer_callback(self):
        """Periodic status update."""
        # Publish status
        status_msg = String()
        status_msg.data = f"{self.robot_name}: {'ENABLED' if self.enabled else 'DISABLED'}, last_cmd={self.last_command}"
        self.status_pub.publish(status_msg)
        
        # Publish command count
        count_msg = Int32()
        count_msg.data = self.command_count
        self.command_count_pub.publish(count_msg)
        
        self.get_logger().info(f"Status: enabled={self.enabled}, commands={self.command_count}")
    
    def destroy_node(self):
        """Clean up before destroying node."""
        self.get_logger().info(f"Shutting down {self.robot_name}")
        self.timer.cancel()
        super().destroy_node()


def main():
    rclpy.init()
    
    node = RobotController()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
