#!/usr/bin/env bash
# Build a macOS wheel that bundles:
#   - Generated ROS message/service/action packages from /opt/fast-dds-v3-libs/python/src
#   - lwrclpy + rclpy sources from this repo
#   - fastdds runtime libs (libfastdds.dylib/libfastcdr.dylib) from /opt/fast-dds-v3/lib
#   - Vendored fastdds Python package (including _fastdds_python.so/.dylib)
# Usage:
#   python3 -m venv venv && source venv/bin/activate
#   bash scripts/mac/mac_make_pip_package_with_runtime.sh
#   pip install dist/lwrclpy-*.whl
set -euo pipefail

# ----- Ensure build dependencies -----
echo "[INFO] Ensuring build dependencies..."
python3 -m pip install --upgrade pip setuptools wheel delocate || true

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
PKG_NAME="lwrclpy"
PKG_VERSION="${PKG_VERSION:-0.3.1}"

BUILD_ROOT="${BUILD_ROOT:-${REPO_ROOT}/._types_python_build_v3}"           # prebuilt DataTypes tree
PY_INSTALL_ROOT="${PY_INSTALL_ROOT:-}"                                     # optional: already-installed DataTypes
FASTDDS_PREFIX="${FASTDDS_PREFIX:-/opt/fast-dds-v3}"

STAGING_ROOT="${REPO_ROOT}/._pip_pkg_lwrclpy_mac"
DIST_DIR="${REPO_ROOT}/dist"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "[FATAL] '$1' not found" >&2; exit 1; }; }
need python3
need rsync

[[ -d "${REPO_ROOT}/lwrclpy" ]] || { echo "[FATAL] lwrclpy/ folder not found"; exit 1; }
[[ -d "${REPO_ROOT}/rclpy" ]] || { echo "[FATAL] rclpy/ folder not found"; exit 1; }
[[ -d "${FASTDDS_PREFIX}/lib" ]] || { echo "[FATAL] ${FASTDDS_PREFIX}/lib not found"; exit 1; }

rm -rf "${STAGING_ROOT}"
mkdir -p "${STAGING_ROOT}" "${DIST_DIR}"

PYXY="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
FASTDDS_PKG_SITE="${FASTDDS_PREFIX}/lib/python${PYXY}/site-packages/fastdds"
FASTDDS_PKG_DIST="${FASTDDS_PREFIX}/lib/python${PYXY}/dist-packages/fastdds"

if [[ -d "${FASTDDS_PKG_SITE}" ]]; then
  FASTDDS_PKG_SRC="${FASTDDS_PKG_SITE}"
elif [[ -d "${FASTDDS_PKG_DIST}" ]]; then
  FASTDDS_PKG_SRC="${FASTDDS_PKG_DIST}"
else
  echo "[FATAL] fastdds package not found:"
  echo "  ${FASTDDS_PKG_SITE}"
  echo "  ${FASTDDS_PKG_DIST}"
  exit 2
fi

[[ -f "${FASTDDS_PREFIX}/lib/libfastdds.dylib" ]] || { echo "[FATAL] ${FASTDDS_PREFIX}/lib/libfastdds.dylib missing"; exit 2; }
[[ -f "${FASTDDS_PREFIX}/lib/libfastcdr.dylib" ]] || { echo "[FATAL] ${FASTDDS_PREFIX}/lib/libfastcdr.dylib missing"; exit 2; }
[[ -f "${FASTDDS_PKG_SRC}/_fastdds_python.so" || -f "${FASTDDS_PKG_SRC}/_fastdds_python.dylib" ]] || {
  echo "[FATAL] fastdds Python extension not found under ${FASTDDS_PKG_SRC}"; exit 2; }

echo "[INFO] Staging generated ROS packages into ${STAGING_ROOT}"
if [[ -n "${PY_INSTALL_ROOT}" ]]; then
  [[ -d "${PY_INSTALL_ROOT}" ]] || { echo "[FATAL] PY_INSTALL_ROOT not found: ${PY_INSTALL_ROOT}"; exit 1; }
  rsync -a "${PY_INSTALL_ROOT}/" "${STAGING_ROOT}/"
else
  [[ -d "${BUILD_ROOT}/src" ]] || {
    echo "[FATAL] BUILD_ROOT/src not found: ${BUILD_ROOT}/src"
    echo "        Provide PY_INSTALL_ROOT to use an existing install tree."
    exit 1
  }
  INSTALL_ROOT="${STAGING_ROOT}" BUILD_ROOT="${BUILD_ROOT}" \
    bash "${REPO_ROOT}/scripts/mac/mac_install_python_types.sh"
fi

echo "[INFO] Patching action types to add ROS 2-style wrapper classes"
if [[ -f "${SCRIPTS_DIR}/patch_action_types.py" ]]; then
  python3 "${SCRIPTS_DIR}/patch_action_types.py" "${STAGING_ROOT}"
else
  echo "[WARN] patch_action_types.py not found, skipping action type patching"
fi

echo "[INFO] Patching service types to add ROS 2-style wrapper classes"
if [[ -f "${SCRIPTS_DIR}/patch_service_types.py" ]]; then
  python3 "${SCRIPTS_DIR}/patch_service_types.py" "${STAGING_ROOT}"
else
  echo "[WARN] patch_service_types.py not found, skipping service type patching"
fi

echo "[INFO] Patching message files to preload dependent libraries"
if [[ -f "${SCRIPTS_DIR}/patch_message_dependencies.py" ]]; then
  python3 "${SCRIPTS_DIR}/patch_message_dependencies.py" "${STAGING_ROOT}"
else
  echo "[WARN] patch_message_dependencies.py not found, skipping message dependency patching"
fi

echo "[INFO] Patching all message packages to preload lwrclpy"
if [[ -f "${SCRIPTS_DIR}/patch_message_preload.py" ]]; then
  python3 "${SCRIPTS_DIR}/patch_message_preload.py" "${STAGING_ROOT}"
else
  echo "[WARN] patch_message_preload.py not found, skipping message preload patching"
fi

echo "[INFO] Staging lwrclpy sources"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/lwrclpy/" "${STAGING_ROOT}/lwrclpy/"

echo "[INFO] Staging rclpy compatibility shim"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/rclpy/" "${STAGING_ROOT}/rclpy/"

echo "[INFO] Staging 'launch' package…"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/launch/" "${STAGING_ROOT}/launch/"

echo "[INFO] Staging 'launch_ros' package…"
rsync -a --exclude='__pycache__' --exclude='*.pyc' "${REPO_ROOT}/launch_ros/" "${STAGING_ROOT}/launch_ros/"

SENSORMSGS_PY_DIR="${REPO_ROOT}/third_party/common_interfaces/sensor_msgs_py/sensor_msgs_py"
if [[ -d "${SENSORMSGS_PY_DIR}" ]]; then
  echo "[INFO] Staging sensor_msgs_py utilities"
  rsync -a --exclude='__pycache__' --exclude='*.pyc' "${SENSORMSGS_PY_DIR}/" "${STAGING_ROOT}/sensor_msgs_py/"
else
  echo "[FATAL] sensor_msgs_py not found at ${SENSORMSGS_PY_DIR}"
  echo "       Run: git submodule update --init --recursive"
  echo "       Or set SKIP_SENSORMSGS_PY=1 to build without pointcloud utilities."
  [[ "${SKIP_SENSORMSGS_PY:-0}" == "1" ]] || exit 2
fi

echo "[INFO] Vendoring Fast DDS native libs"
VEN_LIB_DIR="${STAGING_ROOT}/lwrclpy/_vendor/lib"
mkdir -p "${VEN_LIB_DIR}"
install -m 0644 "${FASTDDS_PREFIX}/lib/libfastdds.dylib" "${VEN_LIB_DIR}/"
install -m 0644 "${FASTDDS_PREFIX}/lib/libfastcdr.dylib" "${VEN_LIB_DIR}/"

# Create versioned symlinks for libfastdds and libfastcdr
echo "[INFO] Creating versioned symlinks for Fast DDS libraries"
(cd "${VEN_LIB_DIR}" && ln -sf libfastdds.dylib libfastdds.3.2.dylib)
(cd "${VEN_LIB_DIR}" && ln -sf libfastcdr.dylib libfastcdr.1.1.dylib)
(cd "${VEN_LIB_DIR}" && ln -sf libfastcdr.dylib libfastcdr.2.dylib)

# Bundle tinyxml2 if present (Homebrew dependency required by Fast DDS)
echo "[INFO] Vendoring tinyxml2 (if available)"
TINYXML2_LIB_DIR=""
for CAND in "/opt/homebrew/opt/tinyxml2/lib" "/usr/local/opt/tinyxml2/lib"; do
  if [[ -d "${CAND}" ]]; then
    TINYXML2_LIB_DIR="${CAND}"
    break
  fi
done
if [[ -n "${TINYXML2_LIB_DIR}" ]]; then
  for f in "${TINYXML2_LIB_DIR}"/libtinyxml2*.dylib; do
    [[ -f "${f}" ]] || continue
    install -m 0644 "${f}" "${VEN_LIB_DIR}/"
  done
else
  echo "[WARN] tinyxml2 not found under /opt/homebrew or /usr/local; continuing without bundling"
fi

# Bundle OpenSSL 3 if present (Homebrew dependency required by Fast DDS)
echo "[INFO] Vendoring OpenSSL 3 (if available)"
OPENSSL_LIB_DIR=""
for CAND in "/opt/homebrew/opt/openssl@3/lib" "/usr/local/opt/openssl@3/lib"; do
  if [[ -d "${CAND}" ]]; then
    OPENSSL_LIB_DIR="${CAND}"
    break
  fi
done
if [[ -n "${OPENSSL_LIB_DIR}" ]]; then
  for f in "${OPENSSL_LIB_DIR}"/libssl*.dylib "${OPENSSL_LIB_DIR}"/libcrypto*.dylib; do
    [[ -f "${f}" ]] || continue
    install -m 0644 "${f}" "${VEN_LIB_DIR}/"
  done
else
  echo "[WARN] openssl@3 not found under /opt/homebrew or /usr/local; continuing without bundling"
fi

echo "[INFO] Vendoring fastdds Python package"
VEN_FASTDDS_PARENT="${STAGING_ROOT}/lwrclpy/_vendor"
VEN_FASTDDS_DIR="${VEN_FASTDDS_PARENT}/fastdds"
mkdir -p "${VEN_FASTDDS_PARENT}"
rsync -a "${FASTDDS_PKG_SRC}/" "${VEN_FASTDDS_DIR}/"

# Ensure Python can import the fastdds extension on macOS (.so expected)
if [[ -f "${VEN_FASTDDS_DIR}/_fastdds_python.dylib" && ! -f "${VEN_FASTDDS_DIR}/_fastdds_python.so" ]]; then
  echo "[INFO] Creating _fastdds_python.so from .dylib in vendored fastdds"
  /bin/cp -p "${VEN_FASTDDS_DIR}/_fastdds_python.dylib" "${VEN_FASTDDS_DIR}/_fastdds_python.so"
fi

# Also copy fastdds to site-packages root so std_msgs etc can import it directly
echo "[INFO] Copying fastdds to site-packages root for direct import"
FASTDDS_ROOT_DIR="${STAGING_ROOT}/fastdds"
rsync -a "${FASTDDS_PKG_SRC}/" "${FASTDDS_ROOT_DIR}/"
if [[ -f "${FASTDDS_ROOT_DIR}/_fastdds_python.dylib" && ! -f "${FASTDDS_ROOT_DIR}/_fastdds_python.so" ]]; then
  echo "[INFO] Creating _fastdds_python.so from .dylib in root fastdds"
  /bin/cp -p "${FASTDDS_ROOT_DIR}/_fastdds_python.dylib" "${FASTDDS_ROOT_DIR}/_fastdds_python.so"
fi

# Fix @rpath in fastdds Python bindings to point to lwrclpy/_vendor/lib
echo "[INFO] Fixing @rpath in fastdds Python bindings"
for FASTDDS_BINDING in "${VEN_FASTDDS_DIR}/_fastdds_python.so" "${FASTDDS_ROOT_DIR}/_fastdds_python.so"; do
  if [[ -f "${FASTDDS_BINDING}" ]]; then
    echo "  Patching ${FASTDDS_BINDING}"
    # Remove old @rpath entries pointing to /opt
    for OLD_RPATH in $(otool -l "${FASTDDS_BINDING}" | grep -A 2 "LC_RPATH" | grep "path " | grep "/opt/" | awk '{print $2}' | tr -d '()'); do
      install_name_tool -delete_rpath "${OLD_RPATH}" "${FASTDDS_BINDING}" 2>/dev/null || true
    done
    # Add new @rpath pointing to lwrclpy/_vendor/lib (relative path)
    if [[ "${FASTDDS_BINDING}" == *"/_vendor/"* ]]; then
      # For vendored binding: @loader_path/../lib
      install_name_tool -add_rpath "@loader_path/../lib" "${FASTDDS_BINDING}" 2>/dev/null || true
    else
      # For root binding: @loader_path/../lwrclpy/_vendor/lib
      install_name_tool -add_rpath "@loader_path/../lwrclpy/_vendor/lib" "${FASTDDS_BINDING}" 2>/dev/null || true
    fi
  fi
done

# Patch binary deps to load bundled tinyxml2 from @rpath
echo "[INFO] Rewriting tinyxml2 dylib references to @rpath (if any)"
for BIN in "${VEN_LIB_DIR}/libfastdds.dylib" "${VEN_LIB_DIR}/libfastcdr.dylib" \
           "${VEN_FASTDDS_DIR}/_fastdds_python.so" "${FASTDDS_ROOT_DIR}/_fastdds_python.so"; do
  [[ -f "${BIN}" ]] || continue
  for DEP in $(otool -L "${BIN}" | awk 'NR>1 {print $1}' | grep 'tinyxml2' || true); do
    base="$(basename "${DEP}")"
    install_name_tool -change "${DEP}" "@rpath/${base}" "${BIN}" 2>/dev/null || true
  done
done

# Normalize tinyxml2 dylib install name to @rpath (avoid absolute Homebrew paths)
echo "[INFO] Rewriting tinyxml2 dylib install names to @rpath (if any)"
for TINY in "${VEN_LIB_DIR}/libtinyxml2"*.dylib; do
  [[ -f "${TINY}" ]] || continue
  install_name_tool -id "@rpath/$(basename "${TINY}")" "${TINY}" 2>/dev/null || true
done

# Patch all generated wrapper .so files to use vendored tinyxml2 via @rpath
echo "[INFO] Patching generated wrappers to use vendored tinyxml2"
while IFS= read -r so; do
  # Remove any absolute /opt/... rpaths
  for OLD_RPATH in $(otool -l "${so}" | grep -A 2 "LC_RPATH" | grep "path " | grep "/opt/" | awk '{print $2}' | tr -d '()'); do
    install_name_tool -delete_rpath "${OLD_RPATH}" "${so}" 2>/dev/null || true
  done
  # Ensure rpath points to lwrclpy/_vendor/lib (relative from message packages)
  install_name_tool -add_rpath "@loader_path/../../lwrclpy/_vendor/lib" "${so}" 2>/dev/null || true
  # Rewrite tinyxml2 deps to @rpath
  for DEP in $(otool -L "${so}" | awk 'NR>1 {print $1}' | grep 'tinyxml2' || true); do
    base="$(basename "${DEP}")"
    install_name_tool -change "${DEP}" "@rpath/${base}" "${so}" 2>/dev/null || true
  done
done < <(find "${STAGING_ROOT}" -type f -name '*.so' ! -path "*/lwrclpy/_vendor/lib/*" | sort)

# Patch binary deps to load bundled OpenSSL from @rpath
echo "[INFO] Rewriting OpenSSL dylib references to @rpath (if any)"
for BIN in "${VEN_LIB_DIR}/libfastdds.dylib" "${VEN_LIB_DIR}/libfastcdr.dylib" \
           "${VEN_FASTDDS_DIR}/_fastdds_python.so" "${FASTDDS_ROOT_DIR}/_fastdds_python.so"; do
  [[ -f "${BIN}" ]] || continue
  for DEP in $(otool -L "${BIN}" | awk 'NR>1 {print $1}' | grep -E 'libssl|libcrypto' || true); do
    base="$(basename "${DEP}")"
    install_name_tool -change "${DEP}" "@rpath/${base}" "${BIN}" 2>/dev/null || true
  done
done

# Ensure vendored OpenSSL dylibs refer to each other via @rpath (avoid Cellar absolute paths)
echo "[INFO] Rewriting OpenSSL dylib self-references to @rpath (if any)"
for SSL in "${VEN_LIB_DIR}/libssl"*.dylib; do
  [[ -f "${SSL}" ]] || continue
  # Normalize libssl install name
  install_name_tool -id "@rpath/$(basename "${SSL}")" "${SSL}" 2>/dev/null || true
  # Rewrite libcrypto dependency inside libssl
  for DEP in $(otool -L "${SSL}" | awk 'NR>1 {print $1}' | grep 'libcrypto' || true); do
    base="$(basename "${DEP}")"
    install_name_tool -change "${DEP}" "@rpath/${base}" "${SSL}" 2>/dev/null || true
  done
done

for CRYPTO in "${VEN_LIB_DIR}/libcrypto"*.dylib; do
  [[ -f "${CRYPTO}" ]] || continue
  # Normalize libcrypto install name
  install_name_tool -id "@rpath/$(basename "${CRYPTO}")" "${CRYPTO}" 2>/dev/null || true
done

# Normalize all binaries to avoid /opt absolute paths (use @rpath to vendor libs)
echo "[INFO] Normalizing all binaries to use @rpath (removing /opt references)"
while IFS= read -r bin; do
  # Remove any absolute /opt rpaths
  for OLD_RPATH in $(otool -l "${bin}" | grep -A 2 "LC_RPATH" | grep "path " | grep "/opt/" | awk '{print $2}' | tr -d '()'); do
    install_name_tool -delete_rpath "${OLD_RPATH}" "${bin}" 2>/dev/null || true
  done
  # Add rpaths pointing to vendored libs (relative to most package locations)
  install_name_tool -add_rpath "@loader_path/../../lwrclpy/_vendor/lib" "${bin}" 2>/dev/null || true
  install_name_tool -add_rpath "@loader_path/../lwrclpy/_vendor/lib" "${bin}" 2>/dev/null || true
  install_name_tool -add_rpath "@loader_path/../lib" "${bin}" 2>/dev/null || true
  # Rewrite any /opt absolute dependency to @rpath/<basename>
  for DEP in $(otool -L "${bin}" | awk 'NR>1 {print $1}' | grep '^/opt/' || true); do
    base="$(basename "${DEP}")"
    install_name_tool -change "${DEP}" "@rpath/${base}" "${bin}" 2>/dev/null || true
  done
done < <(find "${STAGING_ROOT}" -type f \( -name '*.so' -o -name '*.dylib' \) ! -path "*/lwrclpy/_vendor/lib/*" | sort)

echo "[INFO] Writing bootstrap loader"
LWRCLPY_INIT="${STAGING_ROOT}/lwrclpy/__init__.py"
[[ -f "${LWRCLPY_INIT}" ]] || echo "# auto-generated" > "${LWRCLPY_INIT}"
cat > "${STAGING_ROOT}/lwrclpy/_bootstrap_fastdds.py" <<'PY'
import os, sys, ctypes

_pkg_dir = os.path.dirname(__file__)
_vendor_parent = os.path.join(_pkg_dir, "_vendor")
_vendor_lib = os.path.join(_vendor_parent, "lib")

def _preload_libs(root):
    if not os.path.isdir(root):
        return
    for name in sorted(os.listdir(root)):
        if name.endswith(".so") or name.endswith(".dylib") or ".so." in name:
            fp = os.path.join(root, name)
            try:
                ctypes.CDLL(fp, mode=getattr(ctypes, "RTLD_GLOBAL", os.RTLD_GLOBAL))
            except Exception:
                pass

def _preload_ros_msg_libs():
    base = os.path.dirname(_pkg_dir)
    seen = set()
    for dp, _dn, files in sorted(os.walk(base), key=lambda item: item[0]):
        for f in sorted(files):
            if not f.startswith("lib"):
                continue
            if not (f.endswith(".so") or f.endswith(".dylib") or ".so." in f):
                continue
            if f in seen:
                continue
            seen.add(f)
            fp = os.path.join(dp, f)
            try:
                ctypes.CDLL(fp, mode=getattr(ctypes, "RTLD_GLOBAL", os.RTLD_GLOBAL))
            except Exception:
                pass

def ensure_fastdds():
    _preload_libs(_vendor_lib)
    vendor_fastdds = os.path.join(_vendor_parent, "fastdds")
    if not os.path.isdir(vendor_fastdds):
        raise ImportError("Vendored fastdds missing: " + vendor_fastdds)
    if _vendor_parent not in sys.path:
        sys.path.insert(0, _vendor_parent)
    import fastdds  # noqa: F401
    _preload_ros_msg_libs()
PY

if ! grep -q 'ensure_fastdds()' "${LWRCLPY_INIT}"; then
  tmp="${STAGING_ROOT}/.init.tmp"
  {
    echo "from ._bootstrap_fastdds import ensure_fastdds"
    echo "ensure_fastdds()"
    cat "${LWRCLPY_INIT}"
  } > "${tmp}"
  mv -f "${tmp}" "${LWRCLPY_INIT}"
fi

cat > "${STAGING_ROOT}/pyproject.toml" <<'PYPROJECT'
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta:__legacy__"
PYPROJECT

cat > "${STAGING_ROOT}/setup.cfg" <<PYSETUPCFG
[metadata]
name = ${PKG_NAME}
version = ${PKG_VERSION}
description = lwrclpy bundle (macOS) with Fast DDS runtime and generated ROS DataTypes
long_description = Vendored Fast DDS runtime (fastdds package, libfastdds/libfastcdr) and generated ROS message packages.
long_description_content_type = text/plain
author = Your Org

[options]
packages = find:
python_requires = >=3.8
include_package_data = True
zip_safe = False

[options.package_data]
* = **/*.py, **/*.so, **/*.dylib, **/*Wrapper.*
PYSETUPCFG

cat > "${STAGING_ROOT}/setup.py" <<'PYSETUP'
from setuptools import setup
from setuptools.dist import Distribution

class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True

if __name__ == "__main__":
    setup(distclass=BinaryDistribution)
PYSETUP

python3 - <<'PY'
import sys, subprocess
try:
    import build  # noqa
except Exception:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "build"])
PY

( cd "${STAGING_ROOT}" && python3 -m build --wheel --outdir "${DIST_DIR}" )

echo
echo "✅ macOS wheel ready under: ${DIST_DIR}"
ls -1 "${DIST_DIR}/${PKG_NAME}-"*.whl
