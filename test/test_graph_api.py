import unittest

import rclpy
from rclpy.topic_endpoint_info import TopicEndpointTypeEnum
from std_msgs.msg import String


class GraphApiTest(unittest.TestCase):
    def tearDown(self):
        try:
            rclpy.try_shutdown()
        except Exception:
            pass

    def test_local_topic_endpoint_info(self):
        rclpy.init()
        node = rclpy.create_node("graph_api_test")
        try:
            node.create_publisher(String, "chatter", 10)
            node.create_subscription(String, "/chatter", lambda msg: None, 10)

            publishers = node.get_publishers_info_by_topic("chatter")
            subscriptions = node.get_subscriptions_info_by_topic("/chatter")

            self.assertEqual(1, len(publishers))
            self.assertEqual(1, len(subscriptions))
            self.assertEqual(TopicEndpointTypeEnum.PUBLISHER, publishers[0].endpoint_type)
            self.assertEqual(TopicEndpointTypeEnum.SUBSCRIPTION, subscriptions[0].endpoint_type)
            self.assertEqual("graph_api_test", publishers[0].node_name)
            self.assertEqual("/", publishers[0].node_namespace)
            self.assertEqual("std_msgs/msg/String", publishers[0].topic_type)
            self.assertEqual("std_msgs/msg/String", subscriptions[0].topic_type)
            self.assertEqual(1, node.count_publishers("chatter"))
            self.assertEqual(1, node.count_subscribers("/chatter"))
            self.assertIn(("/chatter", ["std_msgs/msg/String"]), node.get_topic_names_and_types())
            self.assertIn(("rt/chatter", ["std_msgs/msg/String"]), node.get_topic_names_and_types(no_demangle=True))
            self.assertIn(
                ("/chatter", ["std_msgs/msg/String"]),
                node.get_publisher_names_and_types_by_node("graph_api_test", "/"),
            )
        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    unittest.main()
