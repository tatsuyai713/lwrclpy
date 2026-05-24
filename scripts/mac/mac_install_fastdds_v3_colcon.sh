#!/usr/bin/env bash
# Install Fast DDS v3 core + fastddsgen + fastdds_python via colcon into /opt/fast-dds-v3 (macOS).
# Applies a macOS-specific Fast DDS patch to drop unsupported thread-affinity calls and
# uses Homebrew standalone Asio headers for the Fast DDS version selected by fastdds_python.repos.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ===== Defaults (override via env or CLI flags) =====
PREFIX_V3="${PREFIX_V3:-/opt/fast-dds-v3}"        # merge-install prefix for the v3 runtime
GEN_PREFIX="${GEN_PREFIX:-/opt/fast-dds-gen-v3}"  # installation prefix for fastddsgen launcher
WS="${WS:-$HOME/fastdds_python_ws}"               # colcon workspace
REPOS_FILE="${REPOS_FILE:-$WS/fastdds_python.repos}"
FASTDDS_PYTHON_REPOS_REF="${FASTDDS_PYTHON_REPOS_REF:-v2.6.1}"
PYBIN="${PYBIN:-python3}"                         # Python used to create the venv
JOBS="${JOBS:-$(/usr/sbin/sysctl -n hw.ncpu 2>/dev/null || echo 4)}"
ASIO_INCLUDE_DIR="${ASIO_INCLUDE_DIR:-}"

# ===== CLI flags =====
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix-v3)   PREFIX_V3="$2"; shift 2;;
    --gen-prefix)  GEN_PREFIX="$2"; shift 2;;
    --ws)          WS="$2"; shift 2;;
    --repos)       REPOS_FILE="$2"; shift 2;;
    --python)      PYBIN="$2"; shift 2;;
    -j|--jobs)     JOBS="$2"; shift 2;;
    --asio-include-dir) ASIO_INCLUDE_DIR="$2"; shift 2;;
    *) echo "[WARN] Unknown arg: $1"; shift;;
  esac
done

# ===== Helpers =====
log(){ echo -e "\033[1;36m[INFO]\033[0m $*"; }
warn(){ echo -e "\033[1;33m[WARN]\033[0m $*" >&2; }
die(){ echo -e "\033[1;31m[FATAL]\033[0m $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || die "'$1' not found"; }

# ===== Homebrew & toolchain =====
if ! command -v brew >/dev/null 2>&1; then
  die "Homebrew not found. Install: https://brew.sh/"
fi
BREW_PREFIX="$(brew --prefix)"
ASIO_INCLUDE_DIR="${ASIO_INCLUDE_DIR:-${BREW_PREFIX}/include}"

log "Installing build deps via Homebrew…"
brew update
brew install ninja git pkg-config tinyxml2 wget curl swig gradle openssl@3 asio openjdk@17

# ===== cmake 3.x (avoid 4.x series) =====
# Pin cmake to the latest 3.x to avoid incompatibilities with Fast DDS build scripts.
_install_cmake3_mac() {
  local cur_ver
  cur_ver="$(cmake --version 2>/dev/null | head -1 | awk '{print $3}' || true)"
  if [[ "${cur_ver}" == 3.* ]]; then
    log "cmake ${cur_ver} (3.x) already installed."
    return 0
  fi
  # Try to install cmake@3 formula (Homebrew may provide versioned taps)
  if brew install cmake@3 2>/dev/null; then
    brew link --overwrite cmake@3 2>/dev/null || true
    return 0
  fi
  # Fallback: install via an isolated venv (Homebrew Python is externally managed).
  log "cmake 3.x not available via Homebrew; installing via local venv…"
  local cmake_venv="${SCRIPT_DIR}/venv"
  "${PYBIN}" -m venv "${cmake_venv}"
  "${cmake_venv}/bin/python" -m pip install -U pip wheel
  "${cmake_venv}/bin/python" -m pip install 'cmake>=3.16,<4'
  export PATH="${cmake_venv}/bin:${PATH}"
}
_install_cmake3_mac

# Java (for Fast-DDS-Gen)
detect_java17_home() {
  local brew_java_prefix
  brew_java_prefix="$(brew --prefix openjdk@17 2>/dev/null || true)"
  local brew_java_home="${brew_java_prefix}/libexec/openjdk.jdk/Contents/Home"
  if [[ -x "${brew_java_home}/bin/java" ]]; then
    echo "${brew_java_home}"
    return 0
  fi
  /usr/libexec/java_home -v 17 2>/dev/null || return 1
}
export JAVA_HOME="$(detect_java17_home)"
export PATH="${JAVA_HOME}/bin:${PATH}"
log "Using JAVA_HOME=${JAVA_HOME}"
java -version

need git; need curl; need "${PYBIN}"

# ===== Workspace & venv =====
log "Preparing workspace at: ${WS}"
rm -rf "${WS}"
mkdir -p "${WS}/src" "${WS}/.deps"
cd "${WS}"

log "Creating venv (.venv) with ${PYBIN}…"
"${PYBIN}" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip wheel
python -m pip install -U colcon-common-extensions vcstool empy

# ===== Fetch repos =====
if [[ ! -f "${REPOS_FILE}" ]]; then
  log "Fetching default repos file (Fast-DDS-python ${FASTDDS_PYTHON_REPOS_REF})…"
  curl -fsSL -o "${REPOS_FILE}" \
    "https://raw.githubusercontent.com/eProsima/Fast-DDS-python/${FASTDDS_PYTHON_REPOS_REF}/fastdds_python.repos"
fi
[[ -f "${REPOS_FILE}" ]] || die "repos file not found: ${REPOS_FILE}"

log "Importing repos into src/…"
vcs import --recursive src < "${REPOS_FILE}"

LOAN_HELPER_PATCH="${ROOT_DIR}/scripts/patch_fastdds_python_loan_helpers.py"
if [[ -f "${LOAN_HELPER_PATCH}" ]]; then
  log "Patching Fast-DDS-python SWIG loan helpers…"
  "${PYBIN}" "${LOAN_HELPER_PATCH}" "${WS}/src" || true
fi

# ===== Standalone Asio headers =====
[[ -f "${ASIO_INCLUDE_DIR}/asio.hpp" ]] || die "Asio include not found at: ${ASIO_INCLUDE_DIR}"
log "Using standalone Asio include dir: ${ASIO_INCLUDE_DIR}"

# ===== Locate Fast-DDS source tree (for info only) =====
log "Locating Fast-DDS source tree under ${WS}/src…"
FASTDDS_DIR="$(find "${WS}/src" -maxdepth 2 -type d \( -iname fastdds -o -iname 'Fast-DDS' \) | head -n1 || true)"
[ -n "${FASTDDS_DIR}" ] && [ -d "${FASTDDS_DIR}" ] || die "fastdds source tree not found under ${WS}/src"
log "Found fastdds at: ${FASTDDS_DIR}"

# ===== macOS-specific Fast DDS patching =====
MAC_AFFINITY_FILE="${FASTDDS_DIR}/src/cpp/utils/threading/threading_osx.ipp"
if [[ -f "${MAC_AFFINITY_FILE}" ]]; then
  if grep -q "LWRCLPY_DISABLE_OSX_AFFINITY_PATCH" "${MAC_AFFINITY_FILE}"; then
    log "macOS affinity patch already applied."
  else
    log "Patching Fast DDS to disable unsupported macOS thread affinity…"
    export MAC_AFFINITY_FILE
    python <<'PY'
from pathlib import Path
import os
import sys

target_path = Path(os.environ["MAC_AFFINITY_FILE"])
marker = "LWRCLPY_DISABLE_OSX_AFFINITY_PATCH"
text = target_path.read_text()
if marker in text:
    sys.exit(0)

needle = "static void configure_current_thread_affinity"
start = text.find(needle)
if start == -1:
    print(f"[patch] Unable to find '{needle}' inside {target_path}", file=sys.stderr)
    sys.exit(1)

brace_pos = text.find('{', start)
if brace_pos == -1:
    print("[patch] Unable to locate opening brace for affinity function", file=sys.stderr)
    sys.exit(1)

depth = 0
end = None
for idx in range(brace_pos, len(text)):
    char = text[idx]
    if char == '{':
        depth += 1
    elif char == '}':
        depth -= 1
        if depth == 0:
            end = idx
            break

if end is None:
    print("[patch] Unable to locate closing brace for affinity function", file=sys.stderr)
    sys.exit(1)

replacement = """static void configure_current_thread_affinity(
        const char* thread_name,
        uint64_t affinity)
{
    (void) thread_name;
    (void) affinity;
    // LWRCLPY_DISABLE_OSX_AFFINITY_PATCH: macOS lacks supported APIs to pin DDS threads, leave as no-op.
}
"""

target_path.write_text(text[:start] + replacement + text[end + 1:])
PY
    unset MAC_AFFINITY_FILE
    log "Applied macOS thread affinity patch to Fast DDS."
  fi
else
  warn "macOS affinity patch skipped; file not found: ${MAC_AFFINITY_FILE}"
fi

# ===== fastddsgen build & install =====
GEN_SRC_DIR="$(find "${WS}/src" -maxdepth 2 -type d \( -iname 'fastddsgen' -o -iname 'Fast-DDS-Gen' \) | head -n 1 || true)"
[[ -n "${GEN_SRC_DIR}" ]] || die "Fast-DDS-Gen repo not found under ${WS}/src"
log "Building fastddsgen from: ${GEN_SRC_DIR}"

# Ensure Java 17 is used for Gradle.
export JAVA_HOME="$(detect_java17_home)"
export PATH="${JAVA_HOME}/bin:${PATH}"
log "Using JAVA_HOME=${JAVA_HOME}"
java -version

sudo mkdir -p "${GEN_PREFIX}"
pushd "${GEN_SRC_DIR}" >/dev/null
  ./gradlew --no-daemon clean assemble
  sudo JAVA_HOME="${JAVA_HOME}" ./gradlew --no-daemon install --install_path="${GEN_PREFIX}"
popd >/dev/null

export PATH="${GEN_PREFIX}/bin:${PATH}"
log "fastddsgen: $(command -v fastddsgen)"

# ===== Probe fastddsgen -python =====
log "Probing fastddsgen -python by real generation…"
PROBE_DIR="$(mktemp -d)"
trap 'rm -rf "${PROBE_DIR}"' EXIT
OUT_DIR="${PROBE_DIR}/out"
mkdir -p "${OUT_DIR}"
cat > "${PROBE_DIR}/Probe.idl" <<'IDL'
module probe { struct Foo { long x; }; };
IDL
set +e
fastddsgen -python -d "${OUT_DIR}" -I "${PROBE_DIR}" -replace "${PROBE_DIR}/Probe.idl" >"${PROBE_DIR}/gen.log" 2>&1
RC=$?
set -e
if [[ $RC -ne 0 ]] || ! find "${OUT_DIR}" -name '*.i' -print -quit | grep -q .; then
  sed -n '1,160p' "${PROBE_DIR}/gen.log" || true
  die "fastddsgen -python probe failed (see above)"
fi
log "fastddsgen -python OK (.i generated)"

# ===== Build the v3 stack + fastdds_python via colcon =====
log "Building with colcon → install to ${PREFIX_V3}"
sudo mkdir -p "${PREFIX_V3}"
sudo chown "$(id -u)":"$(id -g)" "${PREFIX_V3}"

PY_EXEC="$(command -v python)"
CMAKE_PREFIX_PATH="${PREFIX_V3}:${BREW_PREFIX}"

# Best-guess defaults (initial run may be empty)
FOONATHAN_DIR_CAND1="${PREFIX_V3}/lib/foonathan_memory/cmake"
FOONATHAN_DIR_CAND2="${PREFIX_V3}/lib/cmake/foonathan_memory"
FOONATHAN_DIR="${FOONATHAN_DIR_CAND1}"; [[ -d "${FOONATHAN_DIR_CAND2}" ]] && FOONATHAN_DIR="${FOONATHAN_DIR_CAND2}"

FASTCDR_DIR_CAND1="${PREFIX_V3}/lib/cmake/fastcdr"
FASTCDR_DIR_CAND2="${PREFIX_V3}/share/fastcdr/cmake"
FASTCDR_DIR="${FASTCDR_DIR_CAND1}"; [[ -d "${FASTCDR_DIR_CAND2}" ]] && FASTCDR_DIR="${FASTCDR_DIR_CAND2}"

log "Using foonathan_memory_DIR=${FOONATHAN_DIR}"
log "Using fastcdr_DIR=${FASTCDR_DIR}"

# Ensure standalone Asio headers take precedence via explicit -I.
# Fast DDS v3.6.x uses modern Asio APIs such as asio::make_strand.
# Disable SHM transport for stability; re-enable later if needed.
CMAKE_COMMON_ARGS=(
  -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_INSTALL_PREFIX="${PREFIX_V3}"
  -DCMAKE_INSTALL_RPATH="${PREFIX_V3}/lib;${PREFIX_V3}/lib64"
  -DPython3_EXECUTABLE="${PY_EXEC}"
  -DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}"
  -Dfoonathan_memory_DIR="${FOONATHAN_DIR}"
  -Dfastcdr_DIR="${FASTCDR_DIR}"
  -DCMAKE_MACOSX_RPATH=ON
  -DCMAKE_CXX_FLAGS="-I${ASIO_INCLUDE_DIR} -Wno-error=nonnull"
  -DCMAKE_C_FLAGS="-I${ASIO_INCLUDE_DIR}"
  -DFASTDDS_SHM_TRANSPORT_DEFAULT=OFF
)

colcon build \
  --base-paths src \
  --merge-install \
  --install-base "${PREFIX_V3}" \
  --cmake-args "${CMAKE_COMMON_ARGS[@]}" \
  --event-handlers console_cohesion+ status+ \
  --executor sequential \
  --packages-up-to fastdds_python fastdds foonathan_memory_vendor fastcdr \
  --parallel-workers "${JOBS}"

# ===== Export instructions =====
cat <<'EOF'

========================================
✅ Installation completed (macOS, Homebrew Asio + Java 17)

# Add these to your shell (~/.zshrc recommended)
export PATH="$PATH:__GEN_PREFIX__/bin"
export CMAKE_PREFIX_PATH="__PREFIX_V3__:$CMAKE_PREFIX_PATH"
export DYLD_LIBRARY_PATH="__PREFIX_V3__/lib:__PREFIX_V3__/lib64:$DYLD_LIBRARY_PATH"
export PYTHONPATH="__PREFIX_V3__/lib/python$(python -c 'import sys;print("{}.{}".format(*sys.version_info[:2]))')/site-packages:$PYTHONPATH"

# Quick sanity checks
which fastddsgen && fastddsgen -version
python - <<'PY'
import fastdds
print("[OK] fastdds Python available")
print("KEEP_* symbols:", [n for n in dir(fastdds) if "KEEP" in n][:6], "…")
PY

# Notes:
# - Fast DDS v3.6.x needs modern standalone Asio APIs, so Homebrew 'asio' is used via -I.
# - Fast-DDS-Gen v4.3.x needs Java 17; this script prefers Homebrew openjdk@17 even if java_home sees an older JDK.
# - If you need SHM transport, rebuild with -DFASTDDS_SHM_TRANSPORT_DEFAULT=ON after confirming stability.
# - If you experimented earlier, clean: rm -rf build install log && re-run this script.
========================================
EOF | sed "s|__GEN_PREFIX__|${GEN_PREFIX}|g; s|__PREFIX_V3__|${PREFIX_V3}|g"
