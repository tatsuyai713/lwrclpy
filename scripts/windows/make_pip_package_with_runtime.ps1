param(
    [string]$BuildRoot = $(if ($env:BUILD_ROOT) { $env:BUILD_ROOT } else { (Join-Path (Get-Location) "._types_python_build_v3") }),
    [string]$FastDdsPrefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { "C:\fast-dds-v3" }),
    [string]$VcpkgRoot = $(if ($env:VCPKG_ROOT) { $env:VCPKG_ROOT } elseif ($env:VCPKG_INSTALLATION_ROOT) { $env:VCPKG_INSTALLATION_ROOT } else { "C:\vcpkg" }),
    [string]$VcpkgTriplet = $(if ($env:VCPKG_DEFAULT_TRIPLET) { $env:VCPKG_DEFAULT_TRIPLET } else { "x64-windows" }),
    [string]$PackageVersion = $(if ($env:PKG_VERSION) { $env:PKG_VERSION.TrimStart("v") } else { "" })
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRoot = $repoRoot.Path
$stagingRoot = Join-Path $repoRoot "._pip_pkg_lwrclpy_win"
$distDir = Join-Path $repoRoot "dist"
$pkgName = "lwrclpy"

function Copy-Tree($Source, $Destination) {
    if (-not (Test-Path $Source)) {
        throw "Source not found: $Source"
    }
    if (Test-Path $Destination) {
        Remove-Item $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Copy-Item (Join-Path $Source "*") $Destination -Recurse -Force
}

function Get-PackageVersion() {
    if ($PackageVersion) {
        return $PackageVersion.TrimStart("v")
    }
    $tag = git -C $repoRoot describe --tags --exact-match 2>$null
    if ($LASTEXITCODE -eq 0 -and $tag) {
        return $tag.TrimStart("v")
    }
    $latest = git -C $repoRoot tag --list "v[0-9]*" --sort=-v:refname | Select-Object -First 1
    if ($latest) {
        return $latest.TrimStart("v")
    }
    return "0.0.0"
}

$PackageVersion = Get-PackageVersion
Write-Host "[INFO] Package version: $PackageVersion"
Write-Host "[INFO] Build root: $BuildRoot"
Write-Host "[INFO] Fast DDS prefix: $FastDdsPrefix"
Write-Host "[INFO] vcpkg root: $VcpkgRoot"
Write-Host "[INFO] vcpkg triplet: $VcpkgTriplet"

python -m pip install --upgrade pip setuptools wheel build delvewheel

if (Test-Path $stagingRoot) {
    Remove-Item $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

$pyxy = python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
$fastddsSite = Join-Path $FastDdsPrefix "Lib\site-packages\fastdds"
$fastddsAlt = Join-Path $FastDdsPrefix "lib\python$pyxy\site-packages\fastdds"
if (Test-Path $fastddsSite) {
    $fastddsPkg = $fastddsSite
} elseif (Test-Path $fastddsAlt) {
    $fastddsPkg = $fastddsAlt
} else {
    throw "fastdds package not found under $fastddsSite or $fastddsAlt"
}

Write-Host "[INFO] Staging generated ROS packages"
$env:BUILD_ROOT = $BuildRoot
$env:INSTALL_ROOT = $stagingRoot
& (Join-Path $PSScriptRoot "install_python_types.ps1") -BuildRoot $BuildRoot -InstallRoot $stagingRoot

Write-Host "[INFO] Patching generated ROS wrappers"
$patches = @(
    "patch_action_types.py",
    "patch_service_types.py",
    "patch_message_preload.py"
)
foreach ($patch in $patches) {
    $path = Join-Path $repoRoot "scripts\$patch"
    if (Test-Path $path) {
        python $path $stagingRoot
    }
}

Write-Host "[INFO] Staging Python packages"
Copy-Tree (Join-Path $repoRoot "lwrclpy") (Join-Path $stagingRoot "lwrclpy")
Copy-Tree (Join-Path $repoRoot "rclpy") (Join-Path $stagingRoot "rclpy")
Copy-Tree (Join-Path $repoRoot "launch") (Join-Path $stagingRoot "launch")
Copy-Tree (Join-Path $repoRoot "launch_ros") (Join-Path $stagingRoot "launch_ros")

$sensorMsgsPy = Join-Path $repoRoot "third_party\common_interfaces\sensor_msgs_py\sensor_msgs_py"
if (Test-Path $sensorMsgsPy) {
    Copy-Tree $sensorMsgsPy (Join-Path $stagingRoot "sensor_msgs_py")
}

Write-Host "[INFO] Vendoring Fast DDS DLLs"
$vendorParent = Join-Path $stagingRoot "lwrclpy\_vendor"
$vendorLib = Join-Path $vendorParent "lib"
$vendorFastdds = Join-Path $vendorParent "fastdds"
New-Item -ItemType Directory -Path $vendorLib -Force | Out-Null
Copy-Tree $fastddsPkg $vendorFastdds
Copy-Tree $fastddsPkg (Join-Path $stagingRoot "fastdds")

$dllRoots = @(
    (Join-Path $VcpkgRoot "installed\$VcpkgTriplet\bin"),
    (Join-Path $FastDdsPrefix "bin"),
    (Join-Path $FastDdsPrefix "lib"),
    (Join-Path $FastDdsPrefix "Lib\site-packages\fastdds")
) | Where-Object { Test-Path $_ }

$patterns = @("*fastdds*.dll", "*fastcdr*.dll", "*foonathan*.dll", "*tinyxml2*.dll", "libssl*.dll", "libcrypto*.dll", "zlib*.dll")
foreach ($root in $dllRoots) {
    foreach ($pattern in $patterns) {
        Get-ChildItem -Path $root -Filter $pattern -File -ErrorAction SilentlyContinue |
            ForEach-Object { Copy-Item $_.FullName (Join-Path $vendorLib $_.Name) -Force }
    }
}

$bootstrap = @'
import os, sys, ctypes

_pkg_dir = os.path.dirname(__file__)
_vendor_parent = os.path.join(_pkg_dir, "_vendor")
_vendor_lib = os.path.join(_vendor_parent, "lib")

def _add_dll_dir(path):
    if os.path.isdir(path):
        try:
            os.add_dll_directory(path)
        except Exception:
            pass

def ensure_fastdds():
    _add_dll_dir(_vendor_lib)
    if _vendor_parent not in sys.path:
        sys.path.insert(0, _vendor_parent)
    for name in ("fastcdr", "fastdds"):
        for filename in sorted(os.listdir(_vendor_lib)) if os.path.isdir(_vendor_lib) else []:
            if name in filename.lower() and filename.lower().endswith(".dll"):
                try:
                    ctypes.WinDLL(os.path.join(_vendor_lib, filename))
                except Exception:
                    pass
    import fastdds  # noqa: F401
'@
Set-Content -Path (Join-Path $stagingRoot "lwrclpy\_bootstrap_fastdds.py") -Value $bootstrap -Encoding UTF8

$init = Join-Path $stagingRoot "lwrclpy\__init__.py"
if (-not (Test-Path $init)) {
    "# auto-generated" | Set-Content -Path $init -Encoding UTF8
}
$initContent = Get-Content $init -Raw
if (-not $initContent.Contains("ensure_fastdds()")) {
    $prefix = "from ._bootstrap_fastdds import ensure_fastdds`nensure_fastdds()`n"
    Set-Content -Path $init -Value ($prefix + $initContent) -Encoding UTF8
}

@"
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta:__legacy__"
"@ | Set-Content -Path (Join-Path $stagingRoot "pyproject.toml") -Encoding UTF8

@"
[metadata]
name = $pkgName
version = $PackageVersion
description = lwrclpy bundle for Windows with Fast DDS runtime and generated ROS DataTypes
long_description = Vendored Fast DDS runtime and generated ROS message packages.
long_description_content_type = text/plain

[options]
packages = find:
python_requires = >=3.8
include_package_data = True
zip_safe = False

[options.package_data]
* = **/*.py, **/*.pyd, **/*.dll, **/*Wrapper.*
"@ | Set-Content -Path (Join-Path $stagingRoot "setup.cfg") -Encoding UTF8

@'
from setuptools import setup
from setuptools.dist import Distribution

class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True

if __name__ == "__main__":
    setup(distclass=BinaryDistribution)
'@ | Set-Content -Path (Join-Path $stagingRoot "setup.py") -Encoding UTF8

Write-Host "[INFO] Building wheel"
Push-Location $stagingRoot
python -m build --wheel --outdir $distDir
Pop-Location

$wheel = Get-ChildItem $distDir -Filter "$pkgName-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) {
    throw "Wheel was not created"
}

Write-Host "[INFO] Repairing wheel with delvewheel"
$wheelhouse = Join-Path $repoRoot "wheelhouse"
New-Item -ItemType Directory -Path $wheelhouse -Force | Out-Null
python -m delvewheel repair $wheel.FullName -w $wheelhouse --add-path $vendorLib

Write-Host "[OK] Windows wheel ready under $wheelhouse"
Get-ChildItem $wheelhouse -Filter "$pkgName-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
