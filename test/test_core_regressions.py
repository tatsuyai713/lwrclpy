#!/usr/bin/env python3
"""Regression tests for core compatibility and side-channel guards."""

import unittest

from lwrclpy.future import Future
from lwrclpy.subscription import _side_channel_matches_payload


class CoreRegressionTests(unittest.TestCase):
    def test_future_result_is_non_blocking_when_pending(self):
        future = Future()
        self.assertIsNone(future.result())
        self.assertIsNone(future.exception())

    def test_cancelled_future_result_matches_rclpy_none(self):
        future = Future()
        self.assertTrue(future.cancel())
        self.assertIsNone(future.result())
        self.assertIsNone(future.exception())

    def test_side_channel_metadata_requires_empty_or_matching_payload(self):
        class Msg:
            pass

        msg = Msg()
        self.assertFalse(_side_channel_matches_payload(msg, "data", 4))

        msg.data = b""
        self.assertTrue(_side_channel_matches_payload(msg, "data", 4))

        msg.data = b"abcd"
        self.assertTrue(_side_channel_matches_payload(msg, "data", 4))

        msg.data = b"abc"
        self.assertFalse(_side_channel_matches_payload(msg, "data", 4))


if __name__ == "__main__":
    unittest.main()
