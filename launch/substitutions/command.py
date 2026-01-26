# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Command substitution - execute a shell command and use output."""

from __future__ import annotations

import subprocess
from typing import Sequence, TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class Command(Substitution):
    """Substitution that executes a command and returns its output."""

    def __init__(
        self,
        command: Sequence['SomeSubstitutionsType'],
        *,
        on_stderr: str = 'warn',
    ):
        """
        Create a Command substitution.

        :param command: The command to execute.
        :param on_stderr: How to handle stderr ('warn', 'ignore', 'fail').
        """
        super().__init__()
        self._command = list(command)
        self._on_stderr = on_stderr

    @property
    def command(self) -> Sequence['SomeSubstitutionsType']:
        """Get the command."""
        return self._command

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"Command({self._command})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution by executing the command."""
        # Resolve command parts
        cmd_parts = []
        for part in self._command:
            resolved = context.perform_substitution(part)
            cmd_parts.append(resolved)

        # Execute the command
        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                check=False,
            )
            
            # Handle stderr
            if result.stderr:
                if self._on_stderr == 'fail':
                    raise RuntimeError(f"Command failed with stderr: {result.stderr}")
                elif self._on_stderr == 'warn':
                    import sys
                    print(f"[WARN] Command stderr: {result.stderr}", file=sys.stderr)
            
            return result.stdout.strip()
            
        except FileNotFoundError:
            raise RuntimeError(f"Command not found: {cmd_parts[0]}")
