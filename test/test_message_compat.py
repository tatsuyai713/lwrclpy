#!/usr/bin/env python3
"""Tests for rclpy-style message compatibility helpers."""

import unittest

import rclpy  # noqa: F401 - importing rclpy applies lwrclpy compatibility patches
from geometry_msgs.msg import Pose, Quaternion


class MessageCompatibilityTests(unittest.TestCase):
    def test_submessage_can_be_reused_across_setters(self):
        quat = Quaternion()
        quat.x = 0.0
        quat.y = 0.0
        quat.z = 0.5
        quat.w = 0.5

        first = Pose()
        second = Pose()

        first.orientation(quat)
        second.orientation(quat)

        self.assertAlmostEqual(first.orientation().z(), 0.5)
        self.assertAlmostEqual(second.orientation().z(), 0.5)


if __name__ == "__main__":
    unittest.main()
