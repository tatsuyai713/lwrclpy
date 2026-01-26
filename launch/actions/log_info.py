# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Log info action."""

from __future__ import annotations

import sys
from typing import List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class LogInfo(Action):
    """Action that logs a message."""

    def __init__(
        self,
        *,
        msg: 'SomeSubstitutionsType',
        **kwargs,
    ):
        """
        Create a LogInfo action.

        :param msg: The message to log.
        """
        super().__init__(**kwargs)
        self._msg = msg

    @property
    def msg(self) -> 'SomeSubstitutionsType':
        """Get the message."""
        return self._msg

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute the log action."""
        message = context.perform_substitution(self._msg)
        print(f"[INFO] {message}")
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"LogInfo(msg={self._msg})"
