# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Service for running a launch description."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import threading
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING

from .launch_context import LaunchContext
from .launch_description import LaunchDescription, LaunchDescriptionEntity

if TYPE_CHECKING:
    from .actions.execute_process import ExecuteProcess


class LaunchService:
    """Service for managing the execution of a launch description."""

    def __init__(
        self,
        *,
        argv: Optional[List[str]] = None,
        debug: bool = False,
    ):
        """
        Create a LaunchService.

        :param argv: Command line arguments (default: sys.argv).
        :param debug: If True, enable debug output.
        """
        self._argv = argv if argv is not None else sys.argv
        self._debug = debug
        self._context: Optional[LaunchContext] = None
        self._launch_description: Optional[LaunchDescription] = None
        self._running = False
        self._shutdown_when_idle = False
        self._returncode: int = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running_processes: Set['ExecuteProcess'] = set()
        self._shutdown_requested = False
        self._lock = threading.Lock()

    @property
    def context(self) -> Optional[LaunchContext]:
        """Get the current launch context."""
        return self._context

    @property
    def returncode(self) -> int:
        """Get the return code of the launch service."""
        return self._returncode

    def include_launch_description(self, launch_description: LaunchDescription) -> None:
        """Include a launch description for execution."""
        self._launch_description = launch_description

    def _parse_launch_arguments(self) -> Dict[str, str]:
        """Parse launch arguments from command line."""
        args = {}
        for arg in self._argv[1:]:  # Skip program name
            if ':=' in arg:
                key, value = arg.split(':=', 1)
                args[key] = value
        return args

    async def _visit_entity(
        self,
        entity: LaunchDescriptionEntity,
        context: LaunchContext,
    ) -> None:
        """Visit a single entity and its sub-entities."""
        # Execute the entity
        sub_entities = None
        
        # Check if entity has an async execute method
        if hasattr(entity, 'execute'):
            result = entity.execute(context)
            if asyncio.iscoroutine(result):
                sub_entities = await result
            else:
                sub_entities = result
        elif hasattr(entity, 'visit'):
            result = entity.visit(context)
            if asyncio.iscoroutine(result):
                sub_entities = await result
            else:
                sub_entities = result
        
        # Process sub-entities
        if sub_entities:
            for sub_entity in sub_entities:
                await self._visit_entity(sub_entity, context)

    async def _run_async(self) -> int:
        """Run the launch description asynchronously."""
        if self._launch_description is None:
            return 1

        # Create context with reference to this service
        self._context = LaunchContext(argv=self._argv, launch_service=self)
        
        # Parse and apply command line arguments
        launch_args = self._parse_launch_arguments()
        for key, value in launch_args.items():
            self._context.launch_configurations[key] = value

        self._running = True
        self._shutdown_requested = False

        try:
            # Visit all entities in the launch description
            entities = self._launch_description.entities
            for entity in entities:
                if self._shutdown_requested:
                    break
                await self._visit_entity(entity, self._context)

            # Wait for all running processes to complete
            while self._running and not self._shutdown_when_idle:
                with self._lock:
                    if not self._running_processes:
                        break
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            await self._shutdown_processes()

        return self._returncode

    async def _shutdown_processes(self) -> None:
        """Shutdown all running processes."""
        with self._lock:
            processes = list(self._running_processes)
        
        for process in processes:
            if hasattr(process, 'shutdown'):
                try:
                    await process.shutdown()
                except Exception:
                    pass

    def run(
        self,
        *,
        shutdown_when_idle: bool = False,
    ) -> int:
        """
        Run the launch service.

        :param shutdown_when_idle: If True, shutdown when all actions complete.
        :return: Return code.
        """
        self._shutdown_when_idle = shutdown_when_idle

        # Setup signal handlers
        def signal_handler(sig, frame):
            self._shutdown_requested = True
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._request_shutdown)

        original_sigint = signal.signal(signal.SIGINT, signal_handler)
        original_sigterm = signal.signal(signal.SIGTERM, signal_handler)

        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            return self._loop.run_until_complete(self._run_async())
        except KeyboardInterrupt:
            return 0
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
            if self._loop is not None:
                self._loop.close()
                self._loop = None

    def _request_shutdown(self) -> None:
        """Request shutdown of the launch service."""
        self._shutdown_requested = True
        self._running = False

    def shutdown(self) -> None:
        """Request shutdown of the launch service."""
        self._request_shutdown()

    def register_process(self, process: 'ExecuteProcess') -> None:
        """Register a running process."""
        with self._lock:
            self._running_processes.add(process)

    def unregister_process(self, process: 'ExecuteProcess') -> None:
        """Unregister a running process."""
        with self._lock:
            self._running_processes.discard(process)

    def emit_event(self, event: Dict) -> None:
        """Emit an event to the context."""
        if self._context is not None:
            self._context.emit_event(event)
