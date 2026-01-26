# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Execute a process as a launch action."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import sys
from typing import Any, Dict, IO, List, Mapping, Optional, Sequence, Tuple, TYPE_CHECKING, Union

from .action import Action

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..launch_description import LaunchDescriptionEntity
    from ..some_substitutions_type import SomeSubstitutionsType


class ExecuteProcess(Action):
    """Action that executes a process."""

    def __init__(
        self,
        *,
        cmd: Sequence['SomeSubstitutionsType'],
        name: Optional['SomeSubstitutionsType'] = None,
        cwd: Optional['SomeSubstitutionsType'] = None,
        env: Optional[Mapping[str, 'SomeSubstitutionsType']] = None,
        additional_env: Optional[Mapping[str, 'SomeSubstitutionsType']] = None,
        shell: bool = False,
        sigterm_timeout: float = 5.0,
        sigkill_timeout: float = 5.0,
        emulate_tty: bool = False,
        output: str = 'screen',
        output_format: str = '{output}',
        log_cmd: bool = False,
        on_exit: Optional[Any] = None,
        respawn: bool = False,
        respawn_delay: float = 0.0,
        respawn_max_retries: int = -1,  # -1 = unlimited
        prefix: Optional['SomeSubstitutionsType'] = None,
        cached_output: bool = False,
        **kwargs,
    ):
        """
        Create an ExecuteProcess action.

        :param cmd: The command to execute (list of arguments).
        :param name: Optional name for the process.
        :param cwd: Working directory.
        :param env: Environment variables (replaces current env).
        :param additional_env: Additional environment variables.
        :param shell: Whether to execute through a shell.
        :param sigterm_timeout: Timeout after SIGTERM before SIGKILL.
        :param sigkill_timeout: Timeout after SIGKILL.
        :param emulate_tty: Whether to emulate a TTY.
        :param output: Output handling ('screen', 'log', 'both', 'own_log').
        :param output_format: Format string for output.
        :param log_cmd: Whether to log the command.
        :param on_exit: Callback or actions to execute on exit.
        :param respawn: Whether to respawn on exit.
        :param respawn_delay: Delay before respawning.
        :param respawn_max_retries: Maximum number of respawn retries.
        :param prefix: Command prefix.
        :param cached_output: Whether to cache output.
        """
        super().__init__(**kwargs)
        self._cmd = cmd
        self._name = name
        self._cwd = cwd
        self._env = env
        self._additional_env = additional_env
        self._shell = shell
        self._sigterm_timeout = sigterm_timeout
        self._sigkill_timeout = sigkill_timeout
        self._emulate_tty = emulate_tty
        self._output = output
        self._output_format = output_format
        self._log_cmd = log_cmd
        self._on_exit = on_exit
        self._respawn = respawn
        self._respawn_delay = respawn_delay
        self._respawn_max_retries = respawn_max_retries
        self._prefix = prefix
        self._cached_output = cached_output

        self._process: Optional[asyncio.subprocess.Process] = None
        self._returncode: Optional[int] = None
        self._completed = False
        self._respawn_count = 0

    @property
    def process(self) -> Optional[asyncio.subprocess.Process]:
        """Get the subprocess."""
        return self._process

    @property
    def returncode(self) -> Optional[int]:
        """Get the return code."""
        return self._returncode

    def _resolve_cmd(self, context: 'LaunchContext') -> List[str]:
        """Resolve the command with substitutions."""
        resolved_cmd = []
        for part in self._cmd:
            resolved = context.perform_substitution(part)
            resolved_cmd.append(resolved)
        return resolved_cmd

    def _resolve_env(self, context: 'LaunchContext') -> Dict[str, str]:
        """Resolve environment variables."""
        # Start with current environment
        if self._env is not None:
            env = {}
            for key, value in self._env.items():
                env[key] = context.perform_substitution(value)
        else:
            env = dict(os.environ)

        # Add additional environment variables
        if self._additional_env is not None:
            for key, value in self._additional_env.items():
                env[key] = context.perform_substitution(value)

        # Add context environment
        env.update(context.environment)

        return env

    def _execute_impl(self, context: 'LaunchContext') -> Optional[List['LaunchDescriptionEntity']]:
        """Execute the process."""
        # Resolve command and environment
        cmd = self._resolve_cmd(context)
        env = self._resolve_env(context)
        
        # Resolve working directory
        cwd = None
        if self._cwd is not None:
            cwd = context.perform_substitution(self._cwd)

        # Resolve name
        name = None
        if self._name is not None:
            name = context.perform_substitution(self._name)
        else:
            name = os.path.basename(cmd[0]) if cmd else 'process'

        # Handle prefix
        if self._prefix is not None:
            prefix = context.perform_substitution(self._prefix)
            if prefix:
                prefix_parts = shlex.split(prefix)
                cmd = prefix_parts + cmd

        if self._log_cmd:
            print(f"[INFO] [{name}] cmd: {' '.join(cmd)}")

        # Start the process
        self._start_process_sync(cmd, env, cwd, name, context)

        return None

    def _start_process_sync(
        self,
        cmd: List[str],
        env: Dict[str, str],
        cwd: Optional[str],
        name: str,
        context: 'LaunchContext',
    ) -> None:
        """Start the process synchronously."""
        try:
            # Create a new process group so we can kill all children
            kwargs = dict(
                env=env,
                cwd=cwd,
                stdout=subprocess.PIPE if self._output != 'screen' else None,
                stderr=subprocess.PIPE if self._output != 'screen' else None,
                text=True,
                start_new_session=True,  # Create new process group
            )

            # For shell execution
            if self._shell:
                cmd_str = ' '.join(cmd)
                self._popen = subprocess.Popen(cmd_str, shell=True, **kwargs)
            else:
                self._popen = subprocess.Popen(cmd, **kwargs)
            
            self._process_name = name
            
            # Register with launch service for cleanup
            if hasattr(context, '_launch_service') and context._launch_service is not None:
                context._launch_service.register_process(self)
            
            if self._output == 'screen':
                print(f"[INFO] [{name}] process started with pid [{self._popen.pid}]")

        except FileNotFoundError as e:
            print(f"[ERROR] [{name}] executable not found: {cmd[0]}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"[ERROR] [{name}] failed to start: {e}", file=sys.stderr)
            raise

    async def wait(self) -> int:
        """Wait for the process to complete."""
        if hasattr(self, '_popen') and self._popen is not None:
            self._returncode = self._popen.wait()
            self._completed = True
            return self._returncode
        return -1

    async def shutdown(self) -> None:
        """Shutdown the process."""
        if hasattr(self, '_popen') and self._popen is not None:
            if self._popen.poll() is None:  # Still running
                name = getattr(self, '_process_name', 'process')
                try:
                    # Send SIGTERM to entire process group
                    pgid = os.getpgid(self._popen.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    try:
                        self._popen.wait(timeout=self._sigterm_timeout)
                    except subprocess.TimeoutExpired:
                        # Force kill the entire process group
                        os.killpg(pgid, signal.SIGKILL)
                        self._popen.wait(timeout=self._sigkill_timeout)
                    print(f"[INFO] [{name}] process terminated")
                except ProcessLookupError:
                    pass  # Process already dead
                except Exception as e:
                    # Fallback to direct kill
                    try:
                        self._popen.terminate()
                        self._popen.wait(timeout=1)
                    except Exception:
                        try:
                            self._popen.kill()
                        except Exception:
                            pass

    def describe(self) -> str:
        """Return a description of this action."""
        return f"ExecuteProcess(cmd={self._cmd})"
