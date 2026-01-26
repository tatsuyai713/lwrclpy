# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Text substitution - for literal text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext


class TextSubstitution(Substitution):
    """Substitution that returns literal text."""

    def __init__(self, *, text: str):
        """
        Create a TextSubstitution.

        :param text: The literal text.
        """
        super().__init__()
        self._text = text

    @property
    def text(self) -> str:
        """Get the text."""
        return self._text

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"TextSubstitution('{self._text}')"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution (just return the text)."""
        return self._text
