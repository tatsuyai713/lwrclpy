# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""This launch file substitutions."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext


class ThisLaunchFile(Substitution):
    """Substitution that returns the path to the current launch file."""

    def describe(self) -> str:
        """Return a description of this substitution."""
        return "ThisLaunchFile()"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        if hasattr(context, '_current_launch_file_path'):
            return context._current_launch_file_path
        raise RuntimeError("Current launch file path not available in context")


class ThisLaunchFileDir(Substitution):
    """Substitution that returns the directory of the current launch file."""

    def describe(self) -> str:
        """Return a description of this substitution."""
        return "ThisLaunchFileDir()"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        if hasattr(context, '_current_launch_file_path'):
            return os.path.dirname(context._current_launch_file_path)
        raise RuntimeError("Current launch file path not available in context")
