# Copyright 2024 lwrclpy Authors
# Licensed under the Apache License, Version 2.0

"""Python expression substitution."""

from __future__ import annotations

from typing import Sequence, TYPE_CHECKING

from .substitution import Substitution

if TYPE_CHECKING:
    from ..launch_context import LaunchContext
    from ..some_substitutions_type import SomeSubstitutionsType


class PythonExpression(Substitution):
    """Substitution that evaluates a Python expression."""

    def __init__(
        self,
        expression: Sequence['SomeSubstitutionsType'],
        *,
        python_modules: Sequence[str] = (),
    ):
        """
        Create a PythonExpression substitution.

        :param expression: The Python expression to evaluate.
        :param python_modules: Additional modules to import.
        """
        super().__init__()
        self._expression = list(expression)
        self._python_modules = list(python_modules)

    @property
    def expression(self) -> Sequence['SomeSubstitutionsType']:
        """Get the expression."""
        return self._expression

    def describe(self) -> str:
        """Return a description of this substitution."""
        return f"PythonExpression({self._expression})"

    def perform(self, context: 'LaunchContext') -> str:
        """Perform the substitution by evaluating the expression."""
        # Build the expression string
        expr_parts = []
        for part in self._expression:
            resolved = context.perform_substitution(part)
            expr_parts.append(resolved)
        expression = ''.join(expr_parts)

        # Build namespace with imported modules
        namespace = {
            'math': __import__('math'),
            'os': __import__('os'),
        }
        
        for module_name in self._python_modules:
            try:
                namespace[module_name] = __import__(module_name)
            except ImportError:
                pass

        # Evaluate the expression
        try:
            result = eval(expression, namespace)
            return str(result)
        except Exception as e:
            raise RuntimeError(f"Failed to evaluate Python expression '{expression}': {e}")
