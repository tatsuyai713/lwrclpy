# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Shutdown action."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class Shutdown(Action):
    """Action that requests launch shutdown."""

    def __init__(
        self,
        *,
        reason: 'SomeSubstitutionsType' = 'shutdown requested',
        **kwargs,
    ):
        """
        Create a Shutdown action.

        :param reason: The reason for shutdown.
        """
        super().__init__(**kwargs)
        self._reason = reason

    @property
    def reason(self) -> 'SomeSubstitutionsType':
        """Get the shutdown reason."""
        return self._reason

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Request shutdown."""
        reason_str = context.perform_substitution(self._reason)
        print(f"[INFO] Shutdown requested: {reason_str}")
        
        # Emit shutdown event
        context.emit_event({
            'type': 'shutdown',
            'reason': reason_str,
        })
        
        return None

    def describe(self) -> str:
        """Return a description of this action."""
        return f"Shutdown(reason={self._reason})"
