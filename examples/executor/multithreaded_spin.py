#!/usr/bin/env python3
"""MultiThreadedExecutor demo: two nodes each with its own topic in parallel."""
import threading
import time
import rclpy
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String


def make_talker(name, topic, on_finished):
    node = rclpy.create_node(name)
    pub = node.create_publisher(String, topic, 10)
    msg = String()
    count = {"n": 0}

    def on_timer():
        msg.data = f"{name} msg {count['n']}"
        pub.publish(msg)
        print(f"[{name}] send: {msg.data}")
        count["n"] += 1
        if count["n"] >= 30:
            print(f"[{name}] finished sending {count['n']} messages")
            timer.cancel()
            on_finished(name)
    timer = node.create_timer(0.2, on_timer)
    return node


def make_listener(name, topic):
    node = rclpy.create_node(name)

    def on_msg(msg: String):
        print(f"[{name}] recv: {msg.data}")

    node.create_subscription(String, topic, on_msg, 10)
    return node


def main():
    rclpy.init()
    finished_talkers = set()
    finished_lock = threading.Lock()
    all_done = threading.Event()

    def on_talker_finished(name):
        with finished_lock:
            finished_talkers.add(name)
            if len(finished_talkers) == 2:
                all_done.set()

    talker_a = make_talker("talker_a", "mt/chatter_a", on_talker_finished)
    talker_b = make_talker("talker_b", "mt/chatter_b", on_talker_finished)
    listener_a = make_listener("listener_a", "mt/chatter_a")
    listener_b = make_listener("listener_b", "mt/chatter_b")

    executor = MultiThreadedExecutor()
    for n in (talker_a, talker_b, listener_a, listener_b):
        executor.add_node(n)

    executor_thread = threading.Thread(target=executor.spin, name="executor_spin")
    executor_thread.start()

    try:
        all_done.wait()
        time.sleep(0.5)
    finally:
        executor.shutdown()
        executor_thread.join(timeout=2.0)
        print("Completed 30 messages per talker; shutting down cleanly.")
        for n in (talker_a, talker_b, listener_a, listener_b):
            n.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
