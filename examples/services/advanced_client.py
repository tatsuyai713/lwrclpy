#!/usr/bin/env python3
"""Advanced service client with async patterns.

This example shows:
- Asynchronous service calls with Future
- Timeout handling
- Checking service availability
- Response handling patterns
"""

import time
import rclpy
from std_srvs.srv import SetBool, Trigger


def main():
    rclpy.init()
    
    # Create a node for client
    node = rclpy.create_node("advanced_service_client")
    logger = node.get_logger()
    
    logger.info("=== Advanced Service Client Demo ===\n")
    
    # Create client for SetBool service
    client = node.create_client(SetBool, "/set_mode")
    
    # 1. Check service availability
    logger.info("--- Service Availability ---")
    
    # Wait for DDS discovery
    time.sleep(1.0)
    
    logger.info(f"Service ready: {client.service_is_ready()}")
    
    # Wait for service with timeout
    logger.info("Waiting for service (3 second timeout)...")
    if client.wait_for_service(timeout_sec=3.0):
        logger.info("Service is available!")
    else:
        logger.warn("Service not available. Starting demo server...")
        
        # Create a simple server for demonstration
        def handle_set_bool(request, response):
            logger.info(f"Server received request: data={request.data}")
            response.success = True
            response.message = f"Mode set to {'ON' if request.data else 'OFF'}"
            return response
        
        server = node.create_service(SetBool, "/set_mode", handle_set_bool)
        logger.info("Demo server started")
        
        # Give server time to start
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info("")
    
    # 2. Synchronous-style call
    logger.info("--- Synchronous-style Call ---")
    
    request = SetBool.Request()
    request.data = True
    
    future = client.call_async(request)
    logger.info("Request sent, waiting for response...")
    
    # Spin until response
    start = time.monotonic()
    while rclpy.ok() and not future.done():
        rclpy.spin_once(node, timeout_sec=0.1)
        if time.monotonic() - start > 5.0:
            logger.error("Timeout waiting for response!")
            break
    
    if future.done():
        response = future.result()
        if response:
            logger.info(f"Response: success={response.success}, message='{response.message}'")
        else:
            logger.error("Empty response received")
    
    logger.info("")
    
    # 3. Call with callback
    logger.info("--- Call with Callback ---")
    
    def on_response(future):
        response = future.result()
        if response:
            logger.info(f"[Callback] Response received: {response.message}")
    
    request2 = SetBool.Request()
    request2.data = False
    
    # Wait for the first async request to complete before sending another
    # (lwrclpy only supports one pending service request at a time)
    while not future.done():
        rclpy.spin_once(node, timeout_sec=0.1)
    
    future2 = client.call_async(request2)
    future2.add_done_callback(on_response)
    logger.info("Request sent with callback attached")
    
    # Spin to process
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    logger.info("")
    logger.info("(Note: lwrclpy only supports one pending service request at a time)")
    logger.info("=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
