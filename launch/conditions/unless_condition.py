# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Unless condition - execute action only if condition is false."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .condition import Condition
from .if_condition import _to_bool

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class UnlessCondition(Condition):
    """Condition that evaluates to true if the predicate is false."""

    def __init__(
        self,
        predicate_expression: 'SomeSubstitutionsType',
    ):
        """
        Create an UnlessCondition.

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
        return f"UnlessCondition({self._predicate_expression})"

    def evaluate(self, context: 'LaunchContext') -> bool:
        """Evaluate the condition."""
        value = context.perform_substitution(self._predicate_expression)
        return not _to_bool(value)
