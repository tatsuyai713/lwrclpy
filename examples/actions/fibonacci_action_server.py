#!/usr/bin/env python3
"""Minimal Fibonacci action server built on lwrclpy's ActionServer."""

import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from example_interfaces.action import Fibonacci


class FibonacciActionServer(Node):
    def __init__(self):
        super().__init__("fibonacci_action_server")
        self._action_server = ActionServer(
            self,
            Fibonacci,
            "fibonacci",
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )

    def goal_callback(self, goal_request):
        self.get_logger().info(f"Received goal request: order={goal_request.order}")
        if goal_request.order <= 0:
            self.get_logger().warn("Rejecting goal with non-positive order.")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        self.get_logger().info("Received cancel request.")
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        try:
            self.get_logger().info(f"Executing goal order={goal_handle.request.order}")
            feedback_msg = Fibonacci.Feedback()
            # Use a plain Python list for sequence manipulation to avoid SWIG
            # __getitem__/__setitem__ overload issues on macOS builds.
            seq = [0, 1]

            for i in range(1, goal_handle.request.order):
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                    result = Fibonacci.Result()
                    result.sequence = seq
                    self.get_logger().info("Goal canceled.")
                    return result

                # compute next Fibonacci number using Python ints
                seq.append(seq[i] + seq[i - 1])
                feedback_msg.sequence = seq
                goal_handle.publish_feedback(feedback_msg)
                time.sleep(0.5)

            result = Fibonacci.Result()
            result.sequence = seq
            goal_handle.succeed()
            self.get_logger().info(f"Goal succeeded with sequence: {result.sequence}")
            return result
        except Exception as e:
            # Log exception details to stderr for debugging
            import traceback, sys
            traceback.print_exc(file=sys.stderr)
            self.get_logger().error(f"Exception in execute_callback: {e}")
            # If an exception occurs, return an aborted result
            result = Fibonacci.Result()
            result.sequence = []
            try:
                goal_handle.abort()
            except Exception:
                pass
            return result


def main(args=None):
    try:
        with rclpy.init(args=args):
            action_server = FibonacciActionServer()
            rclpy.spin(action_server)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
