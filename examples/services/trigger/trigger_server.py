#!/usr/bin/env python3
"""Service with Trigger type (empty request).

This example shows:
- Using std_srvs/Trigger
- Service for triggering robot actions
"""

import rclpy
from std_srvs.srv import Trigger


def main():
    rclpy.init()
    node = rclpy.create_node("trigger_server")
    logger = node.get_logger()
    
    logger.info("=== Trigger Service Server ===\n")
    
    # State machine
    state = {"armed": False, "action_count": 0}
    
    def handle_arm(request, response):
        """Handle arm request."""
        if state["armed"]:
            response.success = False
            response.message = "Already armed"
        else:
            state["armed"] = True
            response.success = True
            response.message = "System armed successfully"
        logger.info(f"[arm] success={response.success}, msg={response.message}")
        return response
    
    def handle_disarm(request, response):
        """Handle disarm request."""
        if not state["armed"]:
            response.success = False
            response.message = "Already disarmed"
        else:
            state["armed"] = False
            response.success = True
            response.message = "System disarmed successfully"
        logger.info(f"[disarm] success={response.success}, msg={response.message}")
        return response
    
    def handle_trigger_action(request, response):
        """Handle action trigger."""
        if not state["armed"]:
            response.success = False
            response.message = "Cannot trigger: system not armed"
        else:
            state["action_count"] += 1
            response.success = True
            response.message = f"Action #{state['action_count']} triggered"
        logger.info(f"[trigger] success={response.success}, msg={response.message}")
        return response
    
    def handle_status(request, response):
        """Handle status request."""
        response.success = True
        response.message = f"armed={state['armed']}, actions={state['action_count']}"
        logger.info(f"[status] {response.message}")
        return response
    
    # Create services
    srv_arm = node.create_service(Trigger, "/arm", handle_arm)
    srv_disarm = node.create_service(Trigger, "/disarm", handle_disarm)
    srv_trigger = node.create_service(Trigger, "/trigger_action", handle_trigger_action)
    srv_status = node.create_service(Trigger, "/status", handle_status)
    
    logger.info("Services available:")
    logger.info("  /arm          - Arm the system")
    logger.info("  /disarm       - Disarm the system")
    logger.info("  /trigger_action - Trigger an action (must be armed)")
    logger.info("  /status       - Get current status")
    logger.info("\nWaiting for requests...")
    logger.info("Run trigger_client.py in another terminal\n")
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
