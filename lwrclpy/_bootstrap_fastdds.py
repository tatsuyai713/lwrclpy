import sys
import os
import glob
import ctypes
import platform

def _python_xy():
    vi = sys.version_info
    return f"{vi.major}.{vi.minor}"

def _is_macos():
    return platform.system() == "Darwin"

def _prepend_sys_path(path):
    # Only add absolute, normalized, existing paths
    if not path:
        return
    if not os.path.isabs(path):
        return
    norm = os.path.abspath(path)
    if not os.path.exists(norm):
        return
    if norm not in sys.path:
        sys.path.insert(0, norm)

def _iter_fastdds_paths():
    """Iterate over Python site-packages directories where pip installs packages."""
    import site
    
    # Only check Python site-packages (where pip installs packages)
    user_site = site.getusersitepackages()
    if user_site and os.path.isdir(user_site):
        yield user_site
    
    for sp in site.getsitepackages():
        if os.path.isdir(sp):
            yield sp

def _preload_libs(paths):
    for p in paths:
        try:
            # Only load absolute paths that exist
            if not os.path.isabs(p) or not os.path.exists(p):
                continue
            ctypes.CDLL(p, mode=getattr(ctypes, "RTLD_GLOBAL", os.RTLD_GLOBAL))
        except Exception:
            pass

def _find_message_libs():
    """Find ROS message type libraries in Python site-packages."""
    import site
    candidates = []
    
    # Check user site-packages first (pip install --user)
    user_site = site.getusersitepackages()
    if user_site and os.path.isdir(user_site):
        candidates.append(user_site)
    
    # Then check system site-packages (pip install)
    for sp in site.getsitepackages():
        if os.path.isdir(sp):
            candidates.append(sp)
    
    # Determine library extension based on platform
    lib_ext = '.dylib' if _is_macos() else '.so'
    
    # Known ROS message package patterns
    ros_msg_packages = {
        'action_msgs', 'builtin_interfaces', 'diagnostic_msgs', 'example_interfaces',
        'gazebo_msgs', 'geometry_msgs', 'lifecycle_msgs', 'nav_msgs', 'pendulum_msgs',
        'rcl_interfaces', 'sensor_msgs', 'shape_msgs', 'std_msgs', 'std_srvs',
        'stereo_msgs', 'test_msgs', 'tf2_msgs', 'trajectory_msgs', 'unique_identifier_msgs',
        'visualization_msgs'
    }
    
    # Search for message type libraries in site-packages
    for base in candidates:
        if not os.path.isdir(base):
            continue
        # Look for ROS message packages only
        try:
            for pkg_name in os.listdir(base):
                # Skip non-ROS packages for performance
                if pkg_name not in ros_msg_packages:
                    continue
                    
                pkg_path = os.path.join(base, pkg_name)
                # Skip non-directories, symlinks, and relative paths
                if not os.path.isdir(pkg_path):
                    continue
                if not os.path.isabs(pkg_path):
                    continue
                # Find lib*.so or lib*.dylib files recursively
                try:
                    for root, dirs, files in os.walk(pkg_path, followlinks=False):
                        # Only process absolute paths
                        if not os.path.isabs(root):
                            continue
                        for f in files:
                            if f.startswith('lib') and f.endswith(lib_ext):
                                lib_path = os.path.join(root, f)
                                if os.path.isabs(lib_path) and os.path.exists(lib_path):
                                    yield lib_path
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue

def ensure_fastdds():
    """
    Ensure Fast-DDS Python bindings are available.
    
    This function:
    1. Preloads Fast-DDS libraries from lwrclpy's _vendor directory
    2. Preloads ROS message libraries that depend on Fast-DDS
    3. Sets up Python paths to find fastdds module
    
    Note: All message packages should import lwrclpy first to ensure
    Fast-DDS is loaded before their native libraries are used.
    """
    # 1) Preload vendored Fast-DDS libraries (bundled with lwrclpy)
    try:
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        vendor_parent = os.path.join(pkg_dir, "_vendor")
        vendor_lib = os.path.join(vendor_parent, "lib")
        vendor_fastdds = os.path.join(vendor_parent, "fastdds")
        
        if os.path.isdir(vendor_lib):
            # Preload Fast-DDS libs in dependency order: fastcdr -> fastdds
            if _is_macos():
                # Load libfastcdr first (dependency of libfastdds)
                cdr_libs = glob.glob(os.path.join(vendor_lib, "libfastcdr*.dylib"))
                _preload_libs(cdr_libs)
                # Then load libfastdds
                dds_libs = glob.glob(os.path.join(vendor_lib, "libfastdds*.dylib"))
                _preload_libs(dds_libs)
            else:
                # On Linux, preload all Fast-DDS libraries
                libs = glob.glob(os.path.join(vendor_lib, "libfast*.so*"))
                _preload_libs(libs)
            
            try:
                # On Windows/Python>=3.8 this is required; harmless elsewhere
                os.add_dll_directory(vendor_lib)  # type: ignore[attr-defined]
            except Exception:
                pass
        
        if os.path.isdir(vendor_fastdds):
            _prepend_sys_path(vendor_parent)
    except Exception:
        pass
    
    # 2) Preload message type libraries from Python site-packages
    # This handles dependencies like action_msgs -> unique_identifier_msgs
    try:
        msg_libs = list(_find_message_libs())
        if msg_libs:
            _preload_libs(msg_libs)
    except Exception:
        pass

    # 3) Try to import fastdds module
    try:
        import fastdds  # noqa: F401
        return
    except Exception:
        pass

    # 4) If not found, search in site-packages directories
    for base in _iter_fastdds_paths():
        fastdds_pkg = os.path.join(base, "fastdds")
        if os.path.isdir(fastdds_pkg):
            _prepend_sys_path(base)
            break

    # 5) Add site-packages to sys.path for message packages
    import site
    user_site = site.getusersitepackages()
    if user_site and os.path.isdir(user_site):
        _prepend_sys_path(user_site)
    
    for sp in site.getsitepackages():
        if os.path.isdir(sp):
            _prepend_sys_path(sp)
