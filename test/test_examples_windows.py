#!/usr/bin/env python3
"""Windows example test entrypoint."""

import os
import sys

from examples_test_runner import main


if __name__ == "__main__":
    platform_name = os.environ.get("LWRCLPY_TEST_PLATFORM", "Windows")
    exit_code = main(platform_name)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
