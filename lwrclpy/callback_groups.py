import threading
from typing import Any, Set


class CallbackGroup:
    """Base class for callback groups that control callback execution."""

    def __init__(self):
        self._entities: Set[Any] = set()
        self._lock = threading.Lock()

    def add_entity(self, entity) -> None:
        with self._lock:
            self._entities.add(entity)

    def remove_entity(self, entity) -> None:
        with self._lock:
            self._entities.discard(entity)

    def has_entity(self, entity) -> bool:
        with self._lock:
            return entity in self._entities

    def beginning_execution(self, entity) -> bool:
        return True

    def ending_execution(self, entity) -> None:
        pass

    def can_execute(self, entity) -> bool:
        return True


class MutuallyExclusiveCallbackGroup(CallbackGroup):
    """Allow only one callback at a time within this group."""

    def __init__(self):
        super().__init__()
        self._executing = False
        self._execution_lock = threading.Lock()

    def beginning_execution(self, entity) -> bool:
        with self._execution_lock:
            if self._executing:
                return False
            self._executing = True
            return True

    def ending_execution(self, entity) -> None:
        with self._execution_lock:
            self._executing = False

    def can_execute(self, entity) -> bool:
        with self._execution_lock:
            return not self._executing


class ReentrantCallbackGroup(CallbackGroup):
    """Allow callbacks to execute concurrently and re-enter."""

    def beginning_execution(self, entity) -> bool:
        return True

    def ending_execution(self, entity) -> None:
        pass

    def can_execute(self, entity) -> bool:
        return True


__all__ = ["CallbackGroup", "MutuallyExclusiveCallbackGroup", "ReentrantCallbackGroup"]
