# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Local substitution - for accessing context locals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext


class LocalSubstitution(Substitution):
    """Substitution that returns a local context value."""

    def __init__(
        self,
        expression: str,
    ):
        """
        Create a LocalSubstitution.

        :param expression: The expression to evaluate on the context locals.
        """
        super().__init__()
        self._expression = expression

    @property
    def expression(self) -> str:
        """Get the expression."""
        return self._expression

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"LocalSubstitution('{self._expression}')"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        if hasattr(context, '_locals') and self._expression in context._locals:
            return str(context._locals[self._expression])
        raise KeyError(f"Local '{self._expression}' not found in context")
