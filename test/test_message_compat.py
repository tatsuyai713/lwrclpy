#!/usr/bin/env python3
"""Tests for rclpy-style message compatibility helpers."""

import unittest

import rclpy  # noqa: F401 - importing rclpy applies lwrclpy compatibility patches
from geometry_msgs.msg import Pose, Quaternion
from nav_msgs.msg import Odometry, Path


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

    def test_nested_message_with_fixed_array_can_be_reused(self):
        odom = Odometry()
        pose_with_covariance = odom.pose()

        first = Odometry()
        second = Odometry()

        first.pose(pose_with_covariance)
        second.pose(pose_with_covariance)

        self.assertEqual(36, len(first.pose().covariance()))
        self.assertEqual(36, len(second.pose().covariance()))

    def test_sequence_of_submessages_can_be_reused(self):
        pose = Pose()
        from geometry_msgs.msg import PoseStamped

        pose_stamped = PoseStamped()
        pose_stamped.pose(pose)
        poses = [pose_stamped]

        first = Path()
        second = Path()

        first.poses(poses)
        second.poses(poses)

        self.assertEqual(1, len(first.poses()))
        self.assertEqual(1, len(second.poses()))


if __name__ == "__main__":
    unittest.main()
