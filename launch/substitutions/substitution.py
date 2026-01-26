# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Base substitution class."""

from __future__ import annotations

from typing import List, Text, TYPE_CHECKING

if TYPE_CHECKING:
    from ..launch_context import LaunchContext


class Substitution:
    """Base class for all substitutions."""

    def describe(self) -> str:
        """Return a description of this substitution."""
        return self.__class__.__name__

    def perform(self, context: 'LaunchContext') -> str:
        """
        Perform the substitution and return the result.

        :param context: The launch context.
        :return: The substituted string value.
        """
        raise NotImplementedError("Subclasses must implement perform()")
