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

Known dependencies (from ROS2 IDL definitions):
- action_msgs.msg.GoalInfo → unique_identifier_msgs.msg.UUID
- action_msgs.msg.GoalStatus → action_msgs.msg.GoalInfo → unique_identifier_msgs.msg.UUID
- All ROS2 actions → action_msgs.msg.GoalInfo → unique_identifier_msgs.msg.UUID
- Many message types → builtin_interfaces.msg.Time/Duration

The script is designed to be:
- Idempotent: Can be run multiple times safely
- Generic: Works with any ROS 2 message/action definition
- Extensible: Easy to add new dependency mappings

Usage:
    python patch_message_dependencies.py <install_root>

Example:
    python patch_message_dependencies.py /opt/fast-dds-v3-libs/python/src
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set


# Known message dependencies (package.msg_type -> [dependencies])
# This mapping is based on ROS2 IDL definitions
KNOWN_DEPENDENCIES: Dict[str, List[str]] = {
    # action_msgs dependencies
    'action_msgs.GoalInfo': ['unique_identifier_msgs.UUID', 'builtin_interfaces.Time'],
    'action_msgs.GoalStatus': ['action_msgs.GoalInfo'],  # Transitively includes UUID and Time
    'action_msgs.GoalStatusArray': ['action_msgs.GoalStatus'],
    
    # action_msgs service dependencies
    'action_msgs.CancelGoal': ['action_msgs.GoalInfo', 'unique_identifier_msgs.UUID', 'builtin_interfaces.Time'],
    
    # All ROS2 action types depend on action_msgs (SendGoal, GetResult use GoalInfo)
    # This is a generic pattern - any action in any package will need these
    '__action__': ['action_msgs.GoalInfo', 'unique_identifier_msgs.UUID', 'builtin_interfaces.Time'],
    
    # sensor_msgs with builtin_interfaces
    'sensor_msgs.Image': ['std_msgs.Header'],
    'sensor_msgs.CameraInfo': ['std_msgs.Header'],
    'sensor_msgs.LaserScan': ['std_msgs.Header'],
    'sensor_msgs.PointCloud2': ['std_msgs.Header'],
    'sensor_msgs.Imu': ['std_msgs.Header', 'geometry_msgs.Quaternion', 'geometry_msgs.Vector3'],
    'sensor_msgs.NavSatFix': ['std_msgs.Header', 'sensor_msgs.NavSatStatus'],
    
    # std_msgs.Header is special - it contains builtin_interfaces.Time
    'std_msgs.Header': ['builtin_interfaces.Time'],
    
    # geometry_msgs dependencies
    'geometry_msgs.PoseStamped': ['std_msgs.Header', 'geometry_msgs.Pose'],
    'geometry_msgs.TwistStamped': ['std_msgs.Header', 'geometry_msgs.Twist'],
    'geometry_msgs.TransformStamped': ['std_msgs.Header', 'geometry_msgs.Transform'],
    'geometry_msgs.AccelStamped': ['std_msgs.Header', 'geometry_msgs.Accel'],
    'geometry_msgs.WrenchStamped': ['std_msgs.Header', 'geometry_msgs.Wrench'],
    
    # nav_msgs dependencies
    'nav_msgs.Odometry': ['std_msgs.Header', 'geometry_msgs.PoseWithCovariance', 'geometry_msgs.TwistWithCovariance'],
    'nav_msgs.Path': ['std_msgs.Header', 'geometry_msgs.PoseStamped'],
}


def get_transitive_dependencies(msg_type: str, visited: Set[str] = None) -> List[str]:
    """Get all transitive dependencies for a message type in load order (deepest first)."""
    if visited is None:
        visited = set()
    
    if msg_type in visited:
        return []
    
    visited.add(msg_type)
    deps = []
    
    if msg_type in KNOWN_DEPENDENCIES:
        for dep in KNOWN_DEPENDENCIES[msg_type]:
            # Recursively get transitive dependencies first (depth-first)
            deps.extend(get_transitive_dependencies(dep, visited))
            # Then add the dependency itself
            deps.append(dep)
    
    return deps


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


def patch_file(py_file: Path, install_root: Path) -> bool:
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
    
    # Check if this message/action has dependencies
    deps = get_transitive_dependencies(msg_type)
    
    # For action files, also add generic action dependencies
    if is_action and '__action__' in KNOWN_DEPENDENCIES:
        generic_deps = KNOWN_DEPENDENCIES['__action__']
        # Add generic action dependencies
        for dep in generic_deps:
            if dep not in deps:
                deps.append(dep)
    
    if not deps:
        print(f"  [SKIP] {py_file.relative_to(install_root)}: no known dependencies")
        return False
    
    content = py_file.read_text()
    
    # Check if already patched
    if 'patch_message_dependencies.py' in content:
        print(f"  [SKIP] {py_file.relative_to(install_root)}: already patched")
        return False
    
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
    
    patched = 0
    for py_file in sorted(message_files):
        if patch_file(py_file, install_root):
            patched += 1
    
    print(f"\n[INFO] Patched {patched}/{len(message_files)} files")
    
    if patched > 0:
        print("[INFO] Dependency preloading patches applied successfully")
        print("[INFO] Message types will now correctly load dependent libraries at import time")


if __name__ == '__main__':
    main()
