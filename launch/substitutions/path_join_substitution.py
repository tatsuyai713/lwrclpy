# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Path join substitution."""

from __future__ import annotations

import os
from typing import Sequence, TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class PathJoinSubstitution(Substitution):
    """Substitution that joins path components."""

    def __init__(
        self,
        substitutions: Sequence['SomeSubstitutionsType'],
    ):
        """
        Create a PathJoinSubstitution.

        :param substitutions: The path components to join.
        """
        super().__init__()
        self._substitutions = list(substitutions)

    @property
    def substitutions(self) -> Sequence['SomeSubstitutionsType']:
        """Get the substitutions."""
        return self._substitutions

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"PathJoinSubstitution({self._substitutions})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution by joining paths."""
        parts = []
        for sub in self._substitutions:
            part = context.perform_substitution(sub)
            parts.append(part)
        return os.path.join(*parts) if parts else ''
