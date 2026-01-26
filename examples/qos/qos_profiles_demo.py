#!/usr/bin/env python3
"""Demonstration of various QoS profiles and settings.

This example shows:
- Predefined QoS profiles (sensor_data, services, parameters)
- Custom QoS with lifespan, deadline, liveliness settings
- QoS compatibility between publisher and subscriber
"""

import rclpy
from rclpy.qos import (
    QoSProfile,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSLivelinessPolicy,
    qos_profile_sensor_data,
    qos_profile_services_default,
    qos_profile_parameters,
    Duration,
    INFINITE_DURATION,
)
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node("qos_demo")
    logger = node.get_logger()

    # 1. Using predefined sensor_data QoS (best-effort, volatile, depth=5)
    logger.info("=== Predefined QoS Profiles ===")
    logger.info(f"Sensor Data QoS: reliability={qos_profile_sensor_data.reliability}, "
                f"durability={qos_profile_sensor_data.durability}")
    
    pub_sensor = node.create_publisher(String, "sensor_topic", qos_profile_sensor_data)

    # 2. Using services default QoS
    logger.info(f"Services QoS: reliability={qos_profile_services_default.reliability}, "
                f"depth={qos_profile_services_default.depth}")

    # 3. Custom QoS with advanced settings
    logger.info("\n=== Custom QoS with Advanced Settings ===")
    
    # QoS with deadline (expect message every 100ms)
    qos_with_deadline = QoSProfile(
        depth=10,
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.VOLATILE,
        deadline=Duration(seconds=0, nanoseconds=100_000_000),  # 100ms
    )
    logger.info(f"Deadline QoS: deadline=100ms")

    # QoS with lifespan (messages expire after 1 second)
    qos_with_lifespan = QoSProfile(
        depth=10,
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        lifespan=Duration(seconds=1, nanoseconds=0),  # 1 second
    )
    logger.info(f"Lifespan QoS: lifespan=1s, durability=TRANSIENT_LOCAL")

    # QoS with liveliness (manual assertion required)
    qos_with_liveliness = QoSProfile(
        depth=10,
        reliability=QoSReliabilityPolicy.RELIABLE,
        liveliness=QoSLivelinessPolicy.MANUAL_BY_TOPIC,
        liveliness_lease_duration=Duration(seconds=2, nanoseconds=0),  # 2 seconds
    )
    logger.info(f"Liveliness QoS: liveliness=MANUAL_BY_TOPIC, lease=2s")

    # 4. Creating publisher and subscriber with compatible QoS
    logger.info("\n=== Creating Pub/Sub with Custom QoS ===")
    
    reliable_qos = QoSProfile(
        depth=10,
        history=QoSHistoryPolicy.KEEP_LAST,
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    )
    
    pub = node.create_publisher(String, "qos_demo_topic", reliable_qos)
    
    received_count = [0]
    
    def callback(msg):
        received_count[0] += 1
        logger.info(f"Received: {msg.data}")
    
    sub = node.create_subscription(String, "qos_demo_topic", callback, reliable_qos)

    # Publish some messages
    msg = String()
    rate = node.create_rate(2.0)  # 2 Hz
    
    try:
        for i in range(5):
            msg.data = f"QoS demo message {i}"
            pub.publish(msg)
            logger.info(f"Published: {msg.data}")
            rclpy.spin_once(node, timeout_sec=0.1)
            rate.sleep()
        
        # Process remaining callbacks
        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.1)
        
        logger.info(f"\nTotal messages received: {received_count[0]}")
        
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
