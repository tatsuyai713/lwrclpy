import threading
from typing import Optional, Set, Any


class CallbackGroup:
    """Base class for callback groups that control callback execution."""

    def __init__(self):
        self._entities: Set[Any] = set()
        self._lock = threading.Lock()

    def add_entity(self, entity) -> None:
        """Add an entity (timer, subscription, etc.) to this group."""
        with self._lock:
            self._entities.add(entity)

    def remove_entity(self, entity) -> None:
        """Remove an entity from this group."""
        with self._lock:
            self._entities.discard(entity)

    def has_entity(self, entity) -> bool:
        """Check if entity belongs to this group."""
        with self._lock:
            return entity in self._entities

    def beginning_execution(self, entity) -> bool:
        """Called before executing a callback. Return True if execution should proceed."""
        return True

    def ending_execution(self, entity) -> None:
        """Called after executing a callback."""
        pass

    def can_execute(self, entity) -> bool:
        """Check if the entity's callback can be executed now."""
        return True


class MutuallyExclusiveCallbackGroup(CallbackGroup):
    """Allows only one callback at a time within this group.
    
    Useful for protecting shared resources without explicit locking.
    """

    def __init__(self):
        super().__init__()
        self._executing = False
        self._execution_lock = threading.Lock()

    def beginning_execution(self, entity) -> bool:
        """Try to acquire exclusive execution rights."""
        with self._execution_lock:
            if self._executing:
                return False
            self._executing = True
            return True

    def ending_execution(self, entity) -> None:
        """Release exclusive execution rights."""
        with self._execution_lock:
            self._executing = False

    def can_execute(self, entity) -> bool:
        """Check if no other callback is executing."""
        with self._execution_lock:
            return not self._executing


class ReentrantCallbackGroup(CallbackGroup):
    """Allows callbacks to execute concurrently and re-enter.
    
    Multiple callbacks can run simultaneously, including
    the same callback being called recursively.
    """

    def __init__(self):
        super().__init__()

    def beginning_execution(self, entity) -> bool:
        """Always allow execution."""
        return True

    def ending_execution(self, entity) -> None:
        """No-op for reentrant group."""
        pass

    def can_execute(self, entity) -> bool:
        """Always allow execution."""
        return True


__all__ = ["CallbackGroup", "MutuallyExclusiveCallbackGroup", "ReentrantCallbackGroup"]
