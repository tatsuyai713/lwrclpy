#!/usr/bin/env python3
"""Example test entrypoint for Windows wheels."""

import os
import faulthandler
import sys
import traceback

from examples_test_runner import main


if __name__ == "__main__":
    faulthandler.enable()
    try:
        platform_name = os.environ.get("LWRCLPY_TEST_PLATFORM", "Windows")
        exit_code = main(platform_name)
    except BaseException:
        traceback.print_exc()
        exit_code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(exit_code)
