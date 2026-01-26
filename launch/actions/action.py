# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Base action class."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity


class Action:
    """Base class for all launch actions."""

    def __init__(
        self,
        *,
        condition: Optional[Any] = None,
    ):
        """
        Create an Action.

        :param condition: Optional condition to control execution.
        """
        self._condition = condition

    @property
    def condition(self) -> Optional[Any]:
        """Get the condition for this action."""
        return self._condition

    def execute(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """
        Execute this action.

        :param context: The launch context.
        :return: Optional list of sub-actions to execute.
        """
        # Check condition if present
        if self._condition is not None:
            if hasattr(self._condition, 'evaluate'):
                if not self._condition.evaluate(context):
                    return None
            elif callable(self._condition):
                if not self._condition(context):
                    return None
        
        return self._execute_impl(context)

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Implementation of execute - to be overridden by subclasses."""
        return None

    def visit(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Visit this action (alias for execute)."""
        return self.execute(context)

    def describe(self) -> str:
        """Return a description of this action."""
        return self.__class__.__name__

    def describe_sub_entities(self) -> List['LaunchDescriptionEntity']:
        """Return sub-entities that should always be described."""
        return []

    def describe_conditional_sub_entities(self) -> List['LaunchDescriptionEntity']:
        """Return sub-entities that are conditionally described."""
        return []

    def get_asyncio_future(self) -> Optional[Any]:
        """Get an asyncio Future if this action has one."""
        return None
