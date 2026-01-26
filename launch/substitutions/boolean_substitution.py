# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Boolean substitutions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


def _to_bool(value: str) -> bool:
    """Convert string to boolean."""
    lower = value.lower()
    if lower in ('true', '1', 'yes', 'on'):
        return True
    elif lower in ('false', '0', 'no', 'off'):
        return False
    else:
        raise ValueError(f"Cannot convert '{value}' to boolean")


class NotSubstitution(Substitution):
    """Substitution that returns the boolean NOT of another substitution."""

    def __init__(
        self,
        value: 'SomeSubstitutionsType',
    ):
        """
        Create a NotSubstitution.

        :param value: The value to negate.
        """
        super().__init__()
        self._value = value

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"NotSubstitution({self._value})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        value_str = context.perform_substitution(self._value)
        result = not _to_bool(value_str)
        return 'true' if result else 'false'


class AndSubstitution(Substitution):
    """Substitution that returns the boolean AND of substitutions."""

    def __init__(
        self,
        left: 'SomeSubstitutionsType',
        right: 'SomeSubstitutionsType',
    ):
        """
        Create an AndSubstitution.

        :param left: The left operand.
        :param right: The right operand.
        """
        super().__init__()
        self._left = left
        self._right = right

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"AndSubstitution({self._left}, {self._right})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        left_str = context.perform_substitution(self._left)
        right_str = context.perform_substitution(self._right)
        result = _to_bool(left_str) and _to_bool(right_str)
        return 'true' if result else 'false'


class OrSubstitution(Substitution):
    """Substitution that returns the boolean OR of substitutions."""

    def __init__(
        self,
        left: 'SomeSubstitutionsType',
        right: 'SomeSubstitutionsType',
    ):
        """
        Create an OrSubstitution.

        :param left: The left operand.
        :param right: The right operand.
        """
        super().__init__()
        self._left = left
        self._right = right

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"OrSubstitution({self._left}, {self._right})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution."""
        left_str = context.perform_substitution(self._left)
        right_str = context.perform_substitution(self._right)
        result = _to_bool(left_str) or _to_bool(right_str)
        return 'true' if result else 'false'
