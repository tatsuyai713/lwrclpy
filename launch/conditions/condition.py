# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Base condition class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..launch_context import LaunchContext


class Condition:
    """Base class for all conditions."""

    def describe(self) -> str:
        """Return a description of this condition."""
        return self.__class__.__name__

    def evaluate(self, context: 'LaunchContext') -> bool:
        """
        Evaluate the condition and return the result.

        :param context: The launch context.
        :return: True if the condition is met, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement evaluate()")
