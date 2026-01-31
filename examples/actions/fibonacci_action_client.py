#!/usr/bin/env python3
"""Minimal Fibonacci action client using the lwrclpy ActionClient."""

import time
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from action_msgs.msg import GoalStatus
from example_interfaces.action import Fibonacci


class FibonacciActionClient(Node):
    def __init__(self):
        super().__init__("fibonacci_action_client")
        self._action_client = ActionClient(self, Fibonacci, "fibonacci")
        self._send_time = None
        self._timeout_sec = 30.0
        self._timer = self.create_timer(1.0, self._check_timeout)

    def _check_timeout(self):
        if self._send_time and (time.time() - self._send_time) > self._timeout_sec:
            self.get_logger().error(f"Action timed out after {self._timeout_sec}s")
            rclpy.shutdown()

    def send_goal(self, order: int):
        self.get_logger().info("Waiting for action server (DDS discovery)...")
        # Wait for DDS discovery between processes (longer on macOS)
        time.sleep(6.0)

        goal_msg = Fibonacci.Goal()
        goal_msg.order = order
        self.get_logger().info(f"Sending goal request order={order}")

        self._send_time = time.time()
        send_goal_future = self._action_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback,
        )
        send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        try:
            goal_handle = future.result()
            if not goal_handle or not goal_handle.accepted:
                self.get_logger().error("Goal rejected :(")
                rclpy.shutdown()
                return
            self.get_logger().info("Goal accepted :)")
            get_result_future = goal_handle.get_result_async()
            get_result_future.add_done_callback(self.get_result_callback)
        except Exception as e:
            self.get_logger().error(f"Goal response error: {e}")
            rclpy.shutdown()

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info(f"Feedback: {feedback.sequence}")

    def get_result_callback(self, future):
        result_msg = future.result()
        result = result_msg.result
        status = result_msg.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info(f"Result: {result.sequence}")
        else:
            self.get_logger().warn(f"Goal finished with status {status}")
        rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    try:
        action_client = FibonacciActionClient()
        action_client.send_goal(order=10)
        rclpy.spin(action_client)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            action_client.destroy_node()
        except:
            pass
        try:
            rclpy.shutdown()
        except:
            pass


if __name__ == "__main__":
    main()
