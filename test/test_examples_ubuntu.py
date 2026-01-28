#!/usr/bin/env python3
"""Example test entrypoint."""

import os
import sys

from examples_test_runner import main


if __name__ == "__main__":
    platform_name = os.environ.get("LWRCLPY_TEST_PLATFORM", "Generic")
    # Don't set LWRCLPY_TEST_USE_INSTALLED=1 to ensure local launch modules are used
    # os.environ["LWRCLPY_TEST_USE_INSTALLED"] = "1"
    exit_code = main(platform_name)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
