# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Launch context for storing configurations and state during launch."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Callable
import os


class LaunchContext:
    """Context object that stores state during launch execution."""

    def __init__(self, *, argv: Optional[List[str]] = None, launch_service: Optional[Any] = None):
        self._argv = argv or []
        self._launch_configurations: Dict[str, str] = {}
        self._configuration_stack: List[Dict[str, str]] = []
        self._environment: Dict[str, str] = dict(os.environ)
        self._locals: Dict[str, Any] = {}
        self._event_handlers: List[Any] = []
        self._is_shutdown = False
        self._shutdown_reason: Optional[str] = None
        self._current_launch_file_path: Optional[str] = None
        self._ros_namespace_stack: List[str] = []
        self._ros_parameters: Dict[str, Any] = {}
        self._ros_parameter_files: List[str] = []
        self._launch_service = launch_service
        
    @property
    def argv(self) -> List[str]:
        """Get command line arguments."""
        return self._argv

    @property
    def launch_configurations(self) -> Dict[str, str]:
        """Get launch configurations dictionary."""
        return self._launch_configurations

    @property
    def environment(self) -> Dict[str, str]:
        """Get environment variables dictionary."""
        return self._environment
    
    def extend_locals(self, local_extensions: Dict[str, Any]) -> None:
        """Extend local context with additional values."""
        self._locals.update(local_extensions)

    def get_locals_as_dict(self) -> Dict[str, Any]:
        """Get a copy of the locals dictionary."""
        return dict(self._locals)

    def perform_substitution(self, substitution) -> str:
        """Perform a substitution and return the result as a string."""
        if substitution is None:
            return ''
        if isinstance(substitution, str):
            return substitution
        if isinstance(substitution, (list, tuple)):
            # Handle list of substitutions (concatenate results)
            parts = []
            for sub in substitution:
                parts.append(self.perform_substitution(sub))
            return ''.join(parts)
        if hasattr(substitution, 'perform'):
            return substitution.perform(self)
        return str(substitution)

    def register_event_handler(self, handler) -> None:
        """Register an event handler."""
        self._event_handlers.append(handler)

    def unregister_event_handler(self, handler) -> None:
        """Unregister an event handler."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
            
    def emit_event(self, event) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers:
            if hasattr(handler, 'handle'):
                handler.handle(event, self)
                
    def emit_event_sync(self, event) -> None:
        """Emit event synchronously."""
        self.emit_event(event)
        
    def would_handle_event(self, event) -> bool:
        """Check if any handler would handle this event."""
        return len(self._event_handlers) > 0

    @property
    def is_shutdown(self) -> bool:
        """Check if shutdown has been requested."""
        return self._is_shutdown

    def _set_is_shutdown(self, value: bool, reason: Optional[str] = None) -> None:
        """Set the shutdown state."""
        self._is_shutdown = value
        self._shutdown_reason = reason

    def _push_configuration_scope(self, forwarding: bool = True) -> None:
        """Push a new configuration scope onto the stack."""
        # Save current configurations
        self._configuration_stack.append(dict(self._launch_configurations))
        
        if not forwarding:
            # Clear configurations for new scope
            self._launch_configurations.clear()

    def _pop_configuration_scope(self) -> None:
        """Pop the current configuration scope from the stack."""
        if self._configuration_stack:
            self._launch_configurations = self._configuration_stack.pop()
