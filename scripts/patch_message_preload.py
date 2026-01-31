#!/usr/bin/env python3
"""
Patch all ROS message package __init__.py files to preload lwrclpy.

This ensures Fast-DDS libraries are loaded before any message type library,
solving the @rpath/libfastdds.3.2.dylib resolution issue on macOS.

The script:
1. Scans all message packages in site-packages
2. For each package, adds 'import lwrclpy' at the top of __init__.py
3. Is idempotent - can be run multiple times safely
4. Works with any ROS message package (current and future)

Usage:
    python patch_message_preload.py [site_packages_dir]

If site_packages_dir is not provided, uses current Python environment's site-packages.
"""
import os
import sys
import site
from pathlib import Path
from typing import List, Set


# Known ROS message package patterns
ROS_MSG_PACKAGES = {
    'action_msgs', 'builtin_interfaces', 'diagnostic_msgs', 'example_interfaces',
    'gazebo_msgs', 'geometry_msgs', 'lifecycle_msgs', 'nav_msgs', 'pendulum_msgs',
    'rcl_interfaces', 'sensor_msgs', 'shape_msgs', 'std_msgs', 'std_srvs',
    'stereo_msgs', 'test_msgs', 'tf2_msgs', 'trajectory_msgs', 'unique_identifier_msgs',
    'visualization_msgs', 'rosgraph_msgs', 'composition_interfaces', 'logging_demo',
    'action_tutorials_interfaces', 'example_interfaces'
}


def find_message_packages(site_packages_dir: Path) -> List[Path]:
    """Find all ROS message package directories in site-packages."""
    packages = []
    
    if not site_packages_dir.exists() or not site_packages_dir.is_dir():
        print(f"[WARN] Site-packages directory not found: {site_packages_dir}")
        return packages
    
    # Scan for known packages
    for pkg_name in ROS_MSG_PACKAGES:
        pkg_dir = site_packages_dir / pkg_name
        if pkg_dir.exists() and pkg_dir.is_dir():
            init_file = pkg_dir / "__init__.py"
            if init_file.exists():
                packages.append(pkg_dir)
    
    # Also scan for any package that has msg/, srv/, or action/ subdirectories
    # This handles future packages not in the known list
    try:
        for item in site_packages_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith('_') or item.name.startswith('.'):
                continue
            if item.name in ROS_MSG_PACKAGES:
                continue  # Already handled above
            
            # Check if it looks like a ROS message package
            has_msg = (item / 'msg').exists()
            has_srv = (item / 'srv').exists()
            has_action = (item / 'action').exists()
            
            if has_msg or has_srv or has_action:
                init_file = item / "__init__.py"
                if init_file.exists():
                    packages.append(item)
                    print(f"[INFO] Found additional ROS package: {item.name}")
    except Exception as e:
        print(f"[WARN] Error scanning for additional packages: {e}")
    
    return packages


def is_already_patched(init_file: Path) -> bool:
    """Check if __init__.py already has lwrclpy import."""
    try:
        content = init_file.read_text(encoding='utf-8')
        # Check for various forms of lwrclpy import
        patterns = [
            'import lwrclpy',
            'from lwrclpy import',
            '# Preload Fast-DDS via lwrclpy',
        ]
        return any(pattern in content for pattern in patterns)
    except Exception as e:
        print(f"[WARN] Error reading {init_file}: {e}")
        return False


def patch_init_file(init_file: Path) -> bool:
    """Add lwrclpy import to the top of __init__.py."""
    try:
        # Read existing content
        content = init_file.read_text(encoding='utf-8')
        
        # Prepare the preload statement
        preload_block = """# Preload Fast-DDS via lwrclpy to ensure correct library loading order
try:
    import lwrclpy  # noqa: F401
except ImportError:
    pass  # lwrclpy not installed, continue anyway

"""
        
        # Find the insertion point (after shebang and initial comments/docstrings)
        lines = content.splitlines(keepends=True)
        insert_idx = 0
        
        # Skip shebang
        if lines and lines[0].startswith('#!'):
            insert_idx = 1
        
        # Skip initial docstring or comments
        in_docstring = False
        docstring_char = None
        for i in range(insert_idx, len(lines)):
            line = lines[i].strip()
            
            # Check for docstring start
            if not in_docstring:
                if line.startswith('"""') or line.startswith("'''"):
                    docstring_char = line[:3]
                    in_docstring = True
                    # Check if docstring ends on same line
                    if line.endswith(docstring_char) and len(line) > 6:
                        in_docstring = False
                        insert_idx = i + 1
                elif line.startswith('#'):
                    insert_idx = i + 1
                elif line == '':
                    insert_idx = i + 1
                else:
                    break
            else:
                # Inside docstring, look for end
                if docstring_char in line:
                    in_docstring = False
                    insert_idx = i + 1
        
        # Insert preload block
        patched_lines = lines[:insert_idx] + [preload_block] + lines[insert_idx:]
        patched_content = ''.join(patched_lines)
        
        # Write back
        init_file.write_text(patched_content, encoding='utf-8')
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to patch {init_file}: {e}")
        return False


def main():
    # Determine site-packages directory
    if len(sys.argv) > 1:
        site_packages_dir = Path(sys.argv[1])
    else:
        # Use current Python environment's site-packages
        site_packages_dirs = site.getsitepackages()
        if site.ENABLE_USER_SITE:
            site_packages_dirs.insert(0, site.getusersitepackages())
        
        # Find the first existing site-packages
        site_packages_dir = None
        for sp in site_packages_dirs:
            sp_path = Path(sp)
            if sp_path.exists() and sp_path.is_dir():
                site_packages_dir = sp_path
                break
        
        if not site_packages_dir:
            print("[ERROR] Could not find site-packages directory")
            sys.exit(1)
    
    print(f"[INFO] Scanning for ROS message packages in: {site_packages_dir}")
    
    # Find all message packages
    packages = find_message_packages(site_packages_dir)
    
    if not packages:
        print("[WARN] No ROS message packages found")
        return
    
    print(f"[INFO] Found {len(packages)} ROS message packages")
    
    # Patch each package
    patched_count = 0
    skipped_count = 0
    failed_count = 0
    
    for pkg_dir in packages:
        init_file = pkg_dir / "__init__.py"
        pkg_name = pkg_dir.name
        
        # Check if already patched
        if is_already_patched(init_file):
            print(f"[SKIP] {pkg_name} - already patched")
            skipped_count += 1
            continue
        
        # Apply patch
        print(f"[PATCH] {pkg_name}")
        if patch_init_file(init_file):
            patched_count += 1
        else:
            failed_count += 1
    
    # Summary
    print(f"\n[SUMMARY]")
    print(f"  Patched: {patched_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Failed:  {failed_count}")
    print(f"  Total:   {len(packages)}")
    
    if failed_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
