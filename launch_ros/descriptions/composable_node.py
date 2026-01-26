# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Composable node description."""

from __future__ import annotations

from typing import Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from launch.some_substitutions_type import SomeSubstitutionsType


class ComposableNode:
    """Description of a composable node."""

    def __init__(
        self,
        *,
        package: 'SomeSubstitutionsType',
        plugin: 'SomeSubstitutionsType',
        name: Optional['SomeSubstitutionsType'] = None,
        namespace: Optional['SomeSubstitutionsType'] = None,
        parameters: Optional[Sequence] = None,
        remappings: Optional[Sequence] = None,
        extra_arguments: Optional[Sequence] = None,
    ):
        """
        Create a ComposableNode description.

        Note: lwrclpy does not support component containers, this is for API compatibility.

        :param package: The package containing the component.
        :param plugin: The component plugin name.
        :param name: Optional node name.
        :param namespace: Optional node namespace.
        :param parameters: Optional parameters.
        :param remappings: Optional remappings.
        :param extra_arguments: Optional extra arguments.
        """
        self._package = package
        self._plugin = plugin
        self._name = name
        self._namespace = namespace
        self._parameters = list(parameters) if parameters else []
        self._remappings = list(remappings) if remappings else []
        self._extra_arguments = list(extra_arguments) if extra_arguments else []

    @property
    def package(self) -> 'SomeSubstitutionsType':
        """Get the package."""
        return self._package

    @property
    def plugin(self) -> 'SomeSubstitutionsType':
        """Get the plugin."""
        return self._plugin

    @property
    def name(self) -> Optional['SomeSubstitutionsType']:
        """Get the name."""
        return self._name

    @property
    def namespace(self) -> Optional['SomeSubstitutionsType']:
        """Get the namespace."""
        return self._namespace

    @property
    def parameters(self) -> Sequence:
        """Get the parameters."""
        return self._parameters

    @property
    def remappings(self) -> Sequence:
        """Get the remappings."""
        return self._remappings

    @property
    def extra_arguments(self) -> Sequence:
        """Get the extra arguments."""
        return self._extra_arguments
