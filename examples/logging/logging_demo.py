#!/usr/bin/env python3
"""Demonstration of logging functionality.

This example shows:
- Getting loggers by name
- Different log levels (debug, info, warn, error, fatal)
- Child loggers
- Setting log levels
"""

import rclpy
from rclpy.logging import get_logger, LoggingSeverity, set_logger_level


def main():
    rclpy.init()
    node = rclpy.create_node("logging_demo")
    
    # 1. Using node's built-in logger
    logger = node.get_logger()
    
    logger.info("=== Logging Demo ===")
    logger.info("")
    
    # 2. Different log levels
    logger.info("--- Log Levels ---")
    logger.debug("This is a DEBUG message (may not show by default)")
    logger.info("This is an INFO message")
    logger.warn("This is a WARNING message")
    logger.error("This is an ERROR message")
    logger.fatal("This is a FATAL message")
    logger.info("")
    
    # 3. Getting logger by name
    logger.info("--- Named Loggers ---")
    custom_logger = get_logger("my_custom_logger")
    custom_logger.info("Message from custom logger")
    
    sensor_logger = get_logger("sensor_processor")
    sensor_logger.info("Processing sensor data...")
    sensor_logger.warn("Sensor reading out of range!")
    logger.info("")
    
    # 4. Child loggers
    logger.info("--- Child Loggers ---")
    parent_logger = get_logger("robot")
    arm_logger = parent_logger.get_child("arm")
    gripper_logger = parent_logger.get_child("gripper")
    
    parent_logger.info("Robot initializing...")
    arm_logger.info("Arm moving to position")
    gripper_logger.info("Gripper closing")
    logger.info("")
    
    # 5. Setting log levels
    logger.info("--- Setting Log Levels ---")
    
    verbose_logger = get_logger("verbose_component")
    verbose_logger.set_level(LoggingSeverity.DEBUG)
    verbose_logger.debug("This DEBUG message should now appear")
    verbose_logger.info("This INFO message should appear")
    
    quiet_logger = get_logger("quiet_component")
    quiet_logger.set_level(LoggingSeverity.ERROR)
    quiet_logger.info("This INFO message will NOT appear")
    quiet_logger.error("But this ERROR message will")
    logger.info("")
    
    # 6. Checking effective level
    logger.info("--- Effective Levels ---")
    level = verbose_logger.get_effective_level()
    logger.info(f"verbose_logger effective level: {level.name}")
    
    level = quiet_logger.get_effective_level()
    logger.info(f"quiet_logger effective level: {level.name}")
    logger.info("")
    
    # 7. Throttled logging (simplified - logs every call in this implementation)
    logger.info("--- Throttled Logging ---")
    for i in range(3):
        logger.info_throttle(1.0, f"Throttled message iteration {i}")
    logger.info("(Note: throttling is simplified in lwrclpy)")
    logger.info("")
    
    # 8. Once-only logging
    logger.info("--- Once-Only Logging ---")
    for i in range(3):
        logger.warn_once(f"This warning appears (iteration {i})")
    logger.info("(Note: once-only is simplified in lwrclpy)")
    logger.info("")
    
    # 9. Practical example: component with scoped logging
    logger.info("--- Practical Example ---")
    
    class SensorComponent:
        def __init__(self, name):
            self.logger = get_logger(f"sensor.{name}")
            self.logger.info(f"Sensor {name} initialized")
        
        def read(self, value):
            if value < 0:
                self.logger.error(f"Invalid reading: {value}")
            elif value > 100:
                self.logger.warn(f"Reading above threshold: {value}")
            else:
                self.logger.debug(f"Normal reading: {value}")
    
    temp_sensor = SensorComponent("temperature")
    temp_sensor.read(25)    # Normal
    temp_sensor.read(150)   # Warning
    temp_sensor.read(-10)   # Error
    
    logger.info("")
    logger.info("=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
