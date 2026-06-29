import math
import unittest

from geometry_msgs.msg import TransformStamped
from rclpy.time import Time
from tf2_ros import Buffer


def _transform(parent, child, x=0.0, y=0.0, z=0.0, qw=1.0):
    msg = TransformStamped()
    msg.header.frame_id = parent
    msg.child_frame_id = child
    msg.transform.translation.x = x
    msg.transform.translation.y = y
    msg.transform.translation.z = z
    msg.transform.rotation.w = qw
    return msg


class Tf2PyTest(unittest.TestCase):
    def test_buffer_core_direct_and_chained_lookup(self):
        buffer = Buffer()
        buffer.set_transform(_transform("world", "base", x=1.0), "test")
        buffer.set_transform(_transform("base", "camera", y=2.0), "test")

        self.assertTrue(buffer.can_transform("world", "camera", Time()))
        result = buffer.lookup_transform("world", "camera", Time())

        self.assertTrue(math.isclose(result.transform.translation.x, 1.0))
        self.assertTrue(math.isclose(result.transform.translation.y, 2.0))
        self.assertTrue(math.isclose(result.transform.translation.z, 0.0))


if __name__ == "__main__":
    unittest.main()
