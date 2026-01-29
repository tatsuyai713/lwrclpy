#!/usr/bin/env python3
"""
Patch Fast-DDS Python bindings to use correct @rpath for lwrclpy's vendored libraries.

This fixes the issue where _fastdds_python.so has @rpath pointing to /opt/fast-dds-v3/lib
but the actual libraries are in lwrclpy/_vendor/lib.

Usage:
    python patch_fastdds_rpath.py [site_packages_dir]
"""
import os
import sys
import site
import subprocess
from pathlib import Path


def find_fastdds_binding(site_packages_dir: Path) -> Path:
    """Find _fastdds_python.so in site-packages."""
    fastdds_dir = site_packages_dir / "fastdds"
    if not fastdds_dir.exists():
        raise FileNotFoundError(f"fastdds package not found in {site_packages_dir}")
    
    # Look for _fastdds_python.so
    binding = fastdds_dir / "_fastdds_python.so"
    if binding.exists():
        return binding
    
    raise FileNotFoundError(f"_fastdds_python.so not found in {fastdds_dir}")


def find_lwrclpy_vendor_lib(site_packages_dir: Path) -> Path:
    """Find lwrclpy/_vendor/lib directory."""
    vendor_lib = site_packages_dir / "lwrclpy" / "_vendor" / "lib"
    if not vendor_lib.exists():
        raise FileNotFoundError(f"lwrclpy/_vendor/lib not found in {site_packages_dir}")
    return vendor_lib


def get_rpaths(binary: Path) -> list:
    """Get current @rpath settings from a binary."""
    try:
        result = subprocess.run(
            ["otool", "-l", str(binary)],
            capture_output=True,
            text=True,
            check=True
        )
        
        rpaths = []
        lines = result.stdout.splitlines()
        i = 0
        while i < len(lines):
            if "LC_RPATH" in lines[i]:
                # Next couple lines have the path
                for j in range(i+1, min(i+4, len(lines))):
                    if "path " in lines[j]:
                        path = lines[j].split("path ")[1].split(" (offset")[0].strip()
                        rpaths.append(path)
                        break
            i += 1
        
        return rpaths
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to get rpaths: {e}")
        return []


def remove_rpath(binary: Path, rpath: str):
    """Remove an @rpath from a binary."""
    try:
        subprocess.run(
            ["install_name_tool", "-delete_rpath", rpath, str(binary)],
            check=True,
            capture_output=True
        )
        print(f"  Removed rpath: {rpath}")
    except subprocess.CalledProcessError as e:
        # Ignore error if rpath doesn't exist
        if b"no rpath" not in e.stderr:
            print(f"[WARN] Failed to remove rpath {rpath}: {e.stderr.decode()}")


def add_rpath(binary: Path, rpath: str):
    """Add an @rpath to a binary."""
    try:
        subprocess.run(
            ["install_name_tool", "-add_rpath", rpath, str(binary)],
            check=True,
            capture_output=True
        )
        print(f"  Added rpath: {rpath}")
    except subprocess.CalledProcessError as e:
        # Ignore error if rpath already exists
        if b"already" not in e.stderr and b"duplicate" not in e.stderr:
            print(f"[WARN] Failed to add rpath {rpath}: {e.stderr.decode()}")


def patch_fastdds_rpath(site_packages_dir: Path):
    """Patch Fast-DDS Python bindings to use lwrclpy's vendored libraries."""
    print(f"[INFO] Patching Fast-DDS Python bindings in: {site_packages_dir}")
    
    # Find _fastdds_python.so
    try:
        binding = find_fastdds_binding(site_packages_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return False
    
    print(f"[INFO] Found Fast-DDS binding: {binding}")
    
    # Find lwrclpy/_vendor/lib
    try:
        vendor_lib = find_lwrclpy_vendor_lib(site_packages_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return False
    
    print(f"[INFO] Found lwrclpy vendor lib: {vendor_lib}")
    
    # Get current rpaths
    current_rpaths = get_rpaths(binding)
    print(f"[INFO] Current rpaths: {current_rpaths}")
    
    # Remove old rpaths that point to /opt
    for rpath in current_rpaths:
        if "/opt/" in rpath:
            remove_rpath(binding, rpath)
    
    # Add new rpath pointing to lwrclpy/_vendor/lib
    vendor_lib_abs = vendor_lib.resolve()
    add_rpath(binding, str(vendor_lib_abs))
    
    # Also add @loader_path/../../../lwrclpy/_vendor/lib for relative path
    # This makes the binding relocatable
    relative_path = "@loader_path/../../../lwrclpy/_vendor/lib"
    add_rpath(binding, relative_path)
    
    # Verify
    new_rpaths = get_rpaths(binding)
    print(f"[INFO] New rpaths: {new_rpaths}")
    
    return True


def main():
    # Check if we're on macOS
    if sys.platform != "darwin":
        print("[INFO] This script is only needed on macOS")
        return
    
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
    
    success = patch_fastdds_rpath(site_packages_dir)
    
    if success:
        print("\n[SUCCESS] Fast-DDS Python bindings patched successfully")
    else:
        print("\n[FAILED] Failed to patch Fast-DDS Python bindings")
        sys.exit(1)


if __name__ == '__main__':
    main()
