#!/usr/bin/env python3
"""Action client advanced patterns.

This example shows:
- Sending goals with feedback
- Canceling goals
- Getting result
- Handling multiple goals
"""

import time
import rclpy
from action_msgs.msg import GoalStatus
from example_interfaces.action import Fibonacci


def main():
    rclpy.init()
    node = rclpy.create_node("advanced_action_client")
    logger = node.get_logger()
    
    logger.info("=== Advanced Action Client Demo ===\n")
    
    # Create action client
    from lwrclpy.action import ActionClient
    client = ActionClient(node, Fibonacci, "fibonacci")
    
    logger.info("Waiting for action server...")
    if not client.wait_for_server(timeout_sec=10.0):
        logger.error("Action server not available!")
        node.destroy_node()
        rclpy.shutdown()
        return
    
    logger.info("Action server found!\n")
    
    # 1. Simple goal with result
    logger.info("--- Goal 1: Simple execution ---")
    
    goal = Fibonacci.Goal()
    goal.order(5)
    
    logger.info(f"Sending goal: order={goal.order()}")
    
    # Feedback callback
    def feedback_callback(feedback_msg):
        seq = feedback_msg.partial_sequence()
        logger.info(f"  Feedback: {list(seq)}")
    
    send_goal_future = client.send_goal_async(goal, feedback_callback)
    
    # Wait for goal acceptance
    while not send_goal_future.done():
        rclpy.spin_once(node, timeout_sec=0.1)
    
    goal_handle = send_goal_future.result()
    
    if not goal_handle.accepted:
        logger.error("Goal rejected!")
    else:
        logger.info("Goal accepted, waiting for result...")
        
        # Wait for result
        result_future = goal_handle.get_result_async()
        
        while not result_future.done():
            rclpy.spin_once(node, timeout_sec=0.1)
        
        result = result_future.result()
        sequence = result.sequence()
        logger.info(f"Result: {list(sequence)}")
    
    logger.info("")
    
    # 2. Goal with cancellation
    logger.info("--- Goal 2: Cancellation ---")
    
    goal2 = Fibonacci.Goal()
    goal2.order(10)  # Longer computation
    
    logger.info(f"Sending goal: order={goal2.order()}")
    
    send_goal_future2 = client.send_goal_async(goal2, feedback_callback)
    
    while not send_goal_future2.done():
        rclpy.spin_once(node, timeout_sec=0.1)
    
    goal_handle2 = send_goal_future2.result()
    
    if goal_handle2.accepted:
        logger.info("Goal accepted, waiting briefly then canceling...")
        
        # Wait for some feedback
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.2)
        
        # Cancel the goal
        logger.info("Requesting cancellation...")
        cancel_future = goal_handle2.cancel_goal_async()
        
        while not cancel_future.done():
            rclpy.spin_once(node, timeout_sec=0.1)
        
        cancel_response = cancel_future.result()
        
        # Check status
        result_future2 = goal_handle2.get_result_async()
        while not result_future2.done():
            rclpy.spin_once(node, timeout_sec=0.1)
        
        result2 = result_future2.result()
        logger.info(f"Goal status after cancel: {goal_handle2.status}")
    
    logger.info("")
    
    # 3. Multiple sequential goals
    logger.info("--- Goal 3: Multiple sequential goals ---")
    
    for order in [3, 4, 5]:
        goal = Fibonacci.Goal()
        goal.order(order)
        
        logger.info(f"Sending goal: order={order}")
        
        future = client.send_goal_async(goal)
        while not future.done():
            rclpy.spin_once(node, timeout_sec=0.1)
        
        handle = future.result()
        if handle.accepted:
            result_future = handle.get_result_async()
            while not result_future.done():
                rclpy.spin_once(node, timeout_sec=0.1)
            
            result = result_future.result()
            logger.info(f"  Result: {list(result.sequence())}")
    
    logger.info("\n=== Demo Complete ===")
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
