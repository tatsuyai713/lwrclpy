#!/usr/bin/env python3
"""Patch generated message Python setters for rclpy-compatible submessage reuse.

fastddsgen/SWIG exposes message setters as methods such as ``pose.orientation(q)``.
For nested message fields the generated binding consumes the Python object as an
rvalue reference, so reusing the same object in another setter can fail.  rclpy
messages copy nested values instead.  This build-time patch makes generated
Python setters clone message arguments before passing them into the SWIG layer.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


_METHOD_RE = re.compile(
    r"(?P<indent>    )def (?P<name>[A-Za-z_][A-Za-z_0-9]*)\(self, \*args\):\n"
    r"(?P=indent)    return (?P<wrapper>_[A-Za-z_][A-Za-z_0-9]*Wrapper)\."
    r"(?P<cfunc>[A-Za-z_][A-Za-z_0-9]*)\(self, \*args\)\n"
)


def _should_patch_file(path: Path) -> bool:
    if path.name == "__init__.py" or path.name.startswith("_"):
        return False
    parts = path.parts
    return "msg" in parts and path.suffix == ".py"


def _patch_content(content: str) -> tuple[str, int]:
    if "__LWRCLPY_SUBMESSAGE_SETTER_COMPAT__" in content:
        return content, 0

    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        name = match.group("name")
        if name.startswith("_") or name.startswith("get_") or name in {
            "__eq__",
            "__ne__",
            "__len__",
            "__getitem__",
        }:
            return match.group(0)
        count += 1
        indent = match.group("indent")
        wrapper = match.group("wrapper")
        cfunc = match.group("cfunc")
        return (
            f"{indent}def {name}(self, *args):\n"
            f"{indent}    # __LWRCLPY_SUBMESSAGE_SETTER_COMPAT__\n"
            f"{indent}    if len(args) == 1 and hasattr(args[0], \"this\"):\n"
            f"{indent}        try:\n"
            f"{indent}            from lwrclpy.message_utils import clone_message\n"
            f"{indent}            return {wrapper}.{cfunc}(self, clone_message(args[0], type(args[0])))\n"
            f"{indent}        except Exception:\n"
            f"{indent}            pass\n"
            f"{indent}    return {wrapper}.{cfunc}(self, *args)\n"
        )

    return _METHOD_RE.sub(replace, content), count


def patch_root(root: Path) -> int:
    patched = 0
    for path in root.rglob("*.py"):
        if not _should_patch_file(path):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_content, count = _patch_content(content)
        if count:
            path.write_text(new_content, encoding="utf-8", newline="\n")
            patched += 1
            print(f"[setter-compat] patched {path} ({count} setters)")
    return patched


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <install_root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    if not root.exists():
        print(f"error: {root} does not exist", file=sys.stderr)
        return 2
    patched = patch_root(root)
    print(f"[setter-compat] patched files: {patched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
