#!/usr/bin/env python3
"""
Patch SWIG-generated Python message and action files to preload dependent shared libraries.

This script solves the problem where a type depends on other types (e.g., action_msgs.GoalInfo
depends on unique_identifier_msgs.UUID), but the generated Python file only preloads its own
lib*.so, not the dependencies.

The script:
1. Scans all msg/ and action/ directories in the install root
2. For each .py file, detects if it has a preload section
3. Analyzes dependencies to determine which lib*.so files need to be preloaded
4. Inserts preload code for dependencies before the main lib preload

The script is designed to be:
- Idempotent: Can be run multiple times safely
- Generic: Works from generated SWIG Python modules without a hand-maintained
  dependency table

Usage:
    python patch_message_dependencies.py <install_root>

Example:
    python patch_message_dependencies.py /opt/fast-dds-v3-libs/python/src
"""
import re
import sys
from pathlib import Path
from typing import Dict, List, Set


def get_transitive_dependencies(
    msg_type: str,
    dependency_map: Dict[str, List[str]],
    visited: Set[str] = None,
) -> List[str]:
    """Get all transitive dependencies for a message type in load order (deepest first)."""
    if visited is None:
        visited = set()
    
    if msg_type in visited:
        return []
    
    visited.add(msg_type)
    deps = []
    
    direct_deps = dependency_map.get(msg_type, [])

    if direct_deps:
        for dep in direct_deps:
            # Recursively get transitive dependencies first (depth-first)
            for transitive_dep in get_transitive_dependencies(dep, dependency_map, visited):
                if transitive_dep not in deps:
                    deps.append(transitive_dep)
            # Then add the dependency itself
            if dep not in deps:
                deps.append(dep)
    
    return deps


def _type_from_generated_path(path: Path) -> tuple[str, str, str] | None:
    parts = path.parts
    for subdir in ("msg", "srv", "action"):
        if subdir not in parts:
            continue
        idx = parts.index(subdir)
        if idx <= 0:
            continue
        return parts[idx - 1], subdir, path.stem
    return None


def build_library_index(install_root: Path) -> Dict[str, List[str]]:
    """Map generated type names to package-qualified dependency names."""

    index: Dict[str, List[str]] = {}
    for lib in install_root.rglob("lib*.so"):
        info = _type_from_generated_path(lib)
        if info is None:
            continue
        pkg, subdir, _stem = info
        if subdir != "msg":
            continue
        typ = lib.stem.removeprefix("lib")
        index.setdefault(typ, [])
        qualified = f"{pkg}.{typ}"
        if qualified not in index[typ]:
            index[typ].append(qualified)
    return index


def infer_dependencies_from_generated_python(
    py_file: Path,
    library_index: Dict[str, List[str]],
) -> List[str]:
    """Infer dependent message libraries embedded in a SWIG-generated file.

    fastddsgen emits proxy classes for included message types into the generated
    Python module.  If a proxy class name has a corresponding ``lib<Type>.so`` in
    another generated message package, preload that library before the current
    module's own library.  This keeps custom packages such as fixedsized_msgs
    maintainable without hand-maintaining one entry per message.
    """

    type_info = _type_from_generated_path(py_file)
    if type_info is None:
        return []
    own_pkg, _own_subdir, own_type = type_info
    own_qualified = f"{own_pkg}.{own_type}"
    content = py_file.read_text()

    deps: List[str] = []
    for match in re.finditer(r"(?m)^class\s+([A-Za-z_][A-Za-z_0-9]*)\b", content):
        cls = match.group(1)
        if (
            cls == own_type
            or cls.startswith("_")
            or cls.endswith("Seq")
            or cls.endswith("PubSubType")
            or cls in {"SwigPyIterator", "SwigPyObject"}
        ):
            continue
        for dep in library_index.get(cls, []):
            if dep == own_qualified or dep in deps:
                continue
            deps.append(dep)
    return deps


def build_auto_dependency_map(install_root: Path, message_files: List[Path]) -> Dict[str, List[str]]:
    library_index = build_library_index(install_root)
    dependency_map: Dict[str, List[str]] = {}
    for py_file in message_files:
        type_info = _type_from_generated_path(py_file)
        if type_info is None:
            continue
        pkg, _subdir, typ = type_info
        deps = infer_dependencies_from_generated_python(py_file, library_index)
        if deps:
            dependency_map[f"{pkg}.{typ}"] = deps
    return dependency_map


def find_message_files(install_root: str) -> List[Path]:
    """Find all message, action, and service Python files that have preload sections."""
    install_path = Path(install_root)
    message_files = []
    
    # Find all msg/, action/, and srv/ directories
    for dir_pattern in ['msg', 'action', 'srv']:
        for type_dir in install_path.rglob(dir_pattern):
            if not type_dir.is_dir():
                continue
            
            # Check each .py file
            for py_file in type_dir.glob('*.py'):
                if py_file.name.startswith('_') or py_file.name == '__init__.py':
                    continue
                
                # Check if it has a preload section
                content = py_file.read_text()
                if 'Auto-generated preload' in content and 'ctypes.CDLL' in content:
                    message_files.append(py_file)
    
    return message_files


def extract_message_type(py_file: Path) -> str:
    """Extract message/action/service type from file path (e.g., action_msgs.GoalInfo or action_msgs.CancelGoal)."""
    # Example: /opt/.../action_msgs/msg/GoalInfo.py -> action_msgs.GoalInfo
    # Example: /opt/.../example_interfaces/action/Fibonacci.py -> example_interfaces.Fibonacci (action)
    # Example: /opt/.../action_msgs/srv/CancelGoal.py -> action_msgs.CancelGoal
    parts = py_file.parts
    try:
        # Look for 'msg', 'action', or 'srv' in path
        if 'msg' in parts:
            type_idx = parts.index('msg')
        elif 'srv' in parts:
            type_idx = parts.index('srv')
        elif 'action' in parts:
            type_idx = parts.index('action')
            # For action files, return special marker to use generic action dependencies
            if type_idx > 0:
                package = parts[type_idx - 1]
                action_name = py_file.stem
                # Return both the specific type and a flag that it's an action
                return f"{package}.{action_name}", True
        else:
            return "", False
        
        if type_idx > 0:
            package = parts[type_idx - 1]
            type_name = py_file.stem
            return f"{package}.{type_name}", False
    except (ValueError, IndexError):
        pass
    
    return "", False


def generate_dependency_preload(deps: List[str], install_root: Path, py_file: Path) -> str:
    """Generate preload code for all dependencies of a message/action/service type."""
    if not deps:
        return ""
    
    # Remove duplicates while keeping the first occurrence (deepest dependency)
    seen = set()
    unique_deps = []
    for dep in deps:
        if dep not in seen:
            seen.add(dep)
            unique_deps.append(dep)
    
    preload_lines = ["\n# Preload dependencies (auto-generated by patch_message_dependencies.py)"]
    
    for dep in unique_deps:
        # Convert package.Type to path: package/msg/libType.so or package/srv/libType.so
        pkg, typ = dep.rsplit('.', 1)
        
        # Determine the subdirectory - check if dependency is a service, otherwise assume msg
        # Services like CancelGoal are in srv/, messages in msg/
        subdir = 'msg'
        
        # Calculate relative path from current file to dependency
        # Example: from example_interfaces/action/ to unique_identifier_msgs/msg/
        # Result: ../../unique_identifier_msgs/msg/
        preload_lines.append(f"""
_dep_lib_{typ.lower()} = os.path.join(os.path.dirname(__file__), '..', '..', '{pkg}', '{subdir}', 'lib{typ}.so')
if os.path.exists(_dep_lib_{typ.lower()}):
    try:
        ctypes.CDLL(_dep_lib_{typ.lower()}, mode=getattr(ctypes, 'RTLD_GLOBAL', os.RTLD_GLOBAL))
    except Exception:
        pass""")
    
    return ''.join(preload_lines)


def patch_file(py_file: Path, install_root: Path, dependency_map: Dict[str, List[str]]) -> bool:
    """Patch a single message/action file to add dependency preloads."""
    msg_type_result = extract_message_type(py_file)
    
    if isinstance(msg_type_result, tuple):
        msg_type, is_action = msg_type_result
    else:
        msg_type = msg_type_result
        is_action = False
    
    if not msg_type:
        print(f"  [SKIP] {py_file.relative_to(install_root)}: cannot determine type")
        return False
    
    # Check if this message/action has inferred dependencies.
    deps = get_transitive_dependencies(msg_type, dependency_map)
    
    if not deps:
        print(f"  [SKIP] {py_file.relative_to(install_root)}: no inferred dependencies")
        return False
    
    content = py_file.read_text()
    
    content = re.sub(
        r'\n# Preload dependencies \(auto-generated by patch_message_dependencies\.py\).*?(?=\n_lib_path =)',
        '',
        content,
        flags=re.DOTALL,
    )
    
    # Find the preload section pattern
    # Looking for: "# Auto-generated preload for libXXX.so" followed by "import os, ctypes"
    # Allow for optional whitespace between lines
    preload_pattern = re.compile(
        r'(# Auto-generated preload for lib\w+\.so\s*\n'
        r'import os, ctypes\s*\n)',
        re.MULTILINE
    )
    
    match = preload_pattern.search(content)
    if not match:
        print(f"  [SKIP] {py_file.relative_to(install_root)}: preload section not found")
        return False
    
    # Generate dependency preload code
    dep_preload = generate_dependency_preload(deps, install_root, py_file)
    
    if not dep_preload or dep_preload.strip() == "# Preload dependencies (auto-generated by patch_message_dependencies.py)":
        print(f"  [SKIP] {py_file.relative_to(install_root)}: no preload code generated (deps={len(deps)})")
        return False
    
    # Insert dependency preload after "import os, ctypes"
    new_content = (
        content[:match.end()] +
        dep_preload +
        '\n' +
        content[match.end():]
    )
    
    # Write back
    py_file.write_text(new_content)
    print(f"  [PATCH] {py_file.relative_to(install_root)}: added preloads for {', '.join(deps)}")
    return True


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    
    install_root = Path(sys.argv[1])
    
    if not install_root.exists():
        print(f"[ERROR] Install root does not exist: {install_root}")
        sys.exit(1)
    
    print(f"[INFO] Scanning for message/action/service files in {install_root}")
    message_files = find_message_files(install_root)
    print(f"[INFO] Found {len(message_files)} files with preload sections")
    dependency_map = build_auto_dependency_map(install_root, message_files)
    print(f"[INFO] Inferred dependencies for {len(dependency_map)} generated files")
    
    patched = 0
    for py_file in sorted(message_files):
        if patch_file(py_file, install_root, dependency_map):
            patched += 1
    
    print(f"\n[INFO] Patched {patched}/{len(message_files)} files")
    
    if patched > 0:
        print("[INFO] Dependency preloading patches applied successfully")
        print("[INFO] Message types will now correctly load dependent libraries at import time")


if __name__ == '__main__':
    main()
