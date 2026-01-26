# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Lifecycle node action."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .node import Node

if TYPE_CHECKING:
    from launch.some_substitutions_type import SomeSubstitutionsType


class LifecycleNode(Node):
    """Action to launch a ROS 2 lifecycle node."""

    def __init__(
        self,
        *,
        autostart: bool = False,
        **kwargs,
    ):
        """
        Create a LifecycleNode action.

        :param autostart: Whether to automatically start the node.
        """
        super().__init__(**kwargs)
        self._autostart = autostart

    @property
    def autostart(self) -> bool:
        """Get autostart setting."""
        return self._autostart

    def describe(self) -> str:
        """Return a description of this action."""
        return f"LifecycleNode(autostart={self._autostart})"
