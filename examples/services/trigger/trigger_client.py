#!/usr/bin/env python3
"""Client for Trigger services.

This example shows:
- Calling Trigger services
- Service workflow (arm -> trigger -> disarm)
"""

import time
import rclpy
from std_srvs.srv import Trigger


def call_service(client, node, name):
    """Call a Trigger service and return response."""
    request = Trigger.Request()
    future = client.call_async(request)
    
    # Wait for response
    timeout_start = time.time()
    timeout_sec = 10.0
    while not future.done():
        if time.time() - timeout_start > timeout_sec:
            node.get_logger().error(f"Service {name} call timed out after {timeout_sec}s")
            return None
        rclpy.spin_once(node, timeout_sec=0.1)
    
    return future.result()


def main():
    rclpy.init()
    node = rclpy.create_node("trigger_client")
    logger = node.get_logger()
    
    logger.info("=== Trigger Service Client ===\n")
    
    # Create clients
    client_arm = node.create_client(Trigger, "/arm")
    client_disarm = node.create_client(Trigger, "/disarm")
    client_trigger = node.create_client(Trigger, "/trigger_action")
    client_status = node.create_client(Trigger, "/status")
    
    logger.info("Waiting for DDS discovery...")
    
    # Wait for DDS discovery (no wait_for_service to avoid hanging)
    time.sleep(2.0)
    
    logger.info("Services should be available now!\n")
    
    # 1. Check initial status
    logger.info("--- Checking Status ---")
    resp = call_service(client_status, node, "status")
    if resp is None:
        logger.error("Failed to get status")
        node.destroy_node()
        rclpy.shutdown()
        return
    logger.info(f"Status: {resp.message}\n")
    
    # 2. Try to trigger (should fail - not armed)
    logger.info("--- Trying to Trigger (unarmed) ---")
    resp = call_service(client_trigger, node, "trigger")
    if resp is None:
        logger.error("Failed to trigger")
        node.destroy_node()
        rclpy.shutdown()
        return
    logger.info(f"Result: success={resp.success}, msg={resp.message}\n")
    
    # 3. Arm the system
    logger.info("--- Arming System ---")
    resp = call_service(client_arm, node, "arm")
    if resp is None:
        logger.error("Failed to arm")
        node.destroy_node()
        rclpy.shutdown()
        return
    logger.info(f"Result: success={resp.success}, msg={resp.message}\n")
    
    # 4. Trigger multiple actions
    logger.info("--- Triggering Actions ---")
    for i in range(3):
        resp = call_service(client_trigger, node, "trigger")
        if resp is None:
            logger.error(f"Failed to trigger action {i+1}")
            continue
        logger.info(f"Action {i+1}: success={resp.success}, msg={resp.message}")
        time.sleep(0.3)
    logger.info("")
    
    # 5. Check status
    logger.info("--- Checking Status ---")
    resp = call_service(client_status, node, "status")
    if resp is None:
        logger.error("Failed to get status")
    else:
        logger.info(f"Status: {resp.message}\n")
    
    # 6. Disarm
    logger.info("--- Disarming System ---")
    resp = call_service(client_disarm, node, "disarm")
    if resp is None:
        logger.error("Failed to disarm")
    else:
        logger.info(f"Result: success={resp.success}, msg={resp.message}\n")
    
    # 7. Try to trigger again (should fail)
    logger.info("--- Trying to Trigger (disarmed) ---")
    resp = call_service(client_trigger, node, "trigger")
    if resp is None:
        logger.error("Failed to trigger")
    else:
        logger.info(f"Result: success={resp.success}, msg={resp.message}\n")
    
    logger.info("=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
