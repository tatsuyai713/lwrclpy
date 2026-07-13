#!/usr/bin/env python3
"""Service + client in one process to show round-trip using new API."""
import time
import rclpy
from std_srvs.srv import Trigger


def main():
    rclpy.init()
    node = rclpy.create_node("service_echo_bridge")

    def on_trigger(req: Trigger.Request, res: Trigger.Response):
        res.success = True
        res.message = "pong"
        return res

    srv = node.create_service(Trigger, "ping", on_trigger)
    client = node.create_client(Trigger, "ping")

    # Wait for DDS discovery (in-process should be fast but still needed)
    time.sleep(0.5)
    client.wait_for_service()

    try:
        req = Trigger.Request()
        for i in range(3):
            future = client.call_async(req)
            if not rclpy.spin_until_future_complete(node, future, timeout_sec=1.0):
                raise RuntimeError("Timed out waiting for Trigger response")
            resp = future.result()
            if resp is None:
                raise RuntimeError("Trigger response was empty")
            node.get_logger().info(f"call {i}: success={resp.success} msg={resp.message}")
    finally:
        client.destroy()
        srv.destroy()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
