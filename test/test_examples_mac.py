#!/usr/bin/env python3
"""macOS example test entrypoint."""

import os
import sys

from examples_test_runner import main


if __name__ == "__main__":
    exit_code = main("macOS")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
