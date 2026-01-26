# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""If condition - execute action only if condition is true."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .condition import Condition

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


def _to_bool(value: str) -> bool:
    """Convert string to boolean."""
    lower = value.lower()
    if lower in ('true', '1', 'yes', 'on'):
        return True
    elif lower in ('false', '0', 'no', 'off', ''):
        return False
    else:
        raise ValueError(f"Cannot convert '{value}' to boolean")


class IfCondition(Condition):
    """Condition that evaluates to true if the predicate is true."""

    def __init__(
        self,
        predicate_expression: 'SomeSubstitutionsType',
    ):
        """
        Create an IfCondition.

        :param predicate_expression: Expression that evaluates to a boolean string.
        """
        super().__init__()
        self._predicate_expression = predicate_expression

    @property
    def predicate_expression(self) -> 'SomeSubstitutionsType':
        """Get the predicate expression."""
        return self._predicate_expression

    def describe(self) -> str:
        """Return a description of this condition."""
        return f"IfCondition({self._predicate_expression})"

    def evaluate(self, context: 'LaunchContext') -> bool:
        """Evaluate the condition."""
        value = context.perform_substitution(self._predicate_expression)
        return _to_bool(value)
