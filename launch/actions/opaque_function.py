# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Opaque function action - execute arbitrary Python code."""

from __future__ import annotations

from typing import Callable, List, Optional, TYPE_CHECKING

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity


class OpaqueFunction(Action):
    """Action that executes an arbitrary Python function."""

    def __init__(
        self,
        *,
        function: Callable[..., Optional[List['LaunchDescriptionEntity']]],
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
        **action_kwargs,
    ):
        """
        Create an OpaqueFunction action.

        :param function: The function to execute. Should accept (context, *args, **kwargs).
        :param args: Positional arguments to pass to the function.
        :param kwargs: Keyword arguments to pass to the function.
        """
        super().__init__(**action_kwargs)
        self._function = function
        self._args = args or []
        self._kwargs = kwargs or {}

    @property
    def function(self) -> Callable:
        """Get the function."""
        return self._function

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute the function."""
        return self._function(context, *self._args, **self._kwargs)

    def describe(self) -> str:
        """Return a description of this action."""
        return f"OpaqueFunction(function={self._function.__name__})"
