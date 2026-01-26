# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Launch description that contains actions to be executed."""

from __future__ import annotations
from typing import Any, Iterable, List, Optional, Sequence


class LaunchDescriptionEntity:
    """Base class for entities that can be in a launch description."""
    
    def visit(self, context) -> Optional[List['LaunchDescriptionEntity']]:
        """Visit this entity during launch, returning any sub-entities to also visit."""
        return None

    def describe(self) -> str:
        """Return a description of this entity."""
        return self.__class__.__name__

    def describe_sub_entities(self) -> List['LaunchDescriptionEntity']:
        """Return sub-entities that should always be described."""
        return []

    def describe_conditional_sub_entities(self) -> List['LaunchDescriptionEntity']:
        """Return sub-entities that are conditionally described."""
        return []


class LaunchDescription(LaunchDescriptionEntity):
    """Describes a launch configuration with a list of actions."""

    def __init__(
        self,
        initial_entities: Optional[Iterable[LaunchDescriptionEntity]] = None,
        *,
        deprecated_reason: Optional[str] = None,
    ):
        """
        Create a LaunchDescription.

        :param initial_entities: Optional iterable of LaunchDescriptionEntity to include.
        :param deprecated_reason: Optional deprecation message.
        """
        super().__init__()
        self._entities: List[LaunchDescriptionEntity] = []
        self._deprecated_reason = deprecated_reason
        
        if initial_entities is not None:
            for entity in initial_entities:
                self.add_entity(entity)

    def add_entity(self, entity: LaunchDescriptionEntity) -> None:
        """Add an entity to this launch description."""
        self._entities.append(entity)

    def add_action(self, action: LaunchDescriptionEntity) -> None:
        """Add an action to this launch description (alias for add_entity)."""
        self.add_entity(action)

    @property
    def entities(self) -> List[LaunchDescriptionEntity]:
        """Get the list of entities."""
        return self._entities

    @property
    def deprecated(self) -> bool:
        """Check if this launch description is deprecated."""
        return self._deprecated_reason is not None

    @property
    def deprecated_reason(self) -> Optional[str]:
        """Get the deprecation reason if deprecated."""
        return self._deprecated_reason

    def visit(self, context) -> Optional[List[LaunchDescriptionEntity]]:
        """Visit all entities and return them for processing."""
        return list(self._entities)

    def describe_sub_entities(self) -> List[LaunchDescriptionEntity]:
        """Return all entities for description."""
        return list(self._entities)

    def get_launch_arguments(self) -> List[Any]:
        """Get all declared launch arguments from this description."""
        from .actions import DeclareLaunchArgument
        
        arguments = []
        for entity in self._entities:
            if isinstance(entity, DeclareLaunchArgument):
                arguments.append(entity)
            # Also check sub-entities
            if hasattr(entity, 'describe_sub_entities'):
                for sub_entity in entity.describe_sub_entities():
                    if isinstance(sub_entity, DeclareLaunchArgument):
                        arguments.append(sub_entity)
        return arguments
