param(
    [string]$BuildWorkRoot = $(if ($env:LWRCLPY_WINDOWS_BUILD_ROOT) { $env:LWRCLPY_WINDOWS_BUILD_ROOT } else { "C:\lwrclpy_windows_build" }),
    [string]$BuildRoot = $(if ($env:BUILD_ROOT) { $env:BUILD_ROOT } else { (Join-Path $BuildWorkRoot "generated-types") }),
    [string]$FastDdsPrefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { (Join-Path $BuildWorkRoot "fastdds-prefix") }),
    [string]$VcpkgRoot = $(if ($env:VCPKG_ROOT) { $env:VCPKG_ROOT } elseif ($env:VCPKG_INSTALLATION_ROOT) { $env:VCPKG_INSTALLATION_ROOT } else { (Join-Path $BuildWorkRoot "vcpkg") }),
    [string]$VcpkgTriplet = $(if ($env:VCPKG_DEFAULT_TRIPLET) { $env:VCPKG_DEFAULT_TRIPLET } else { "x64-windows" }),
    [string]$BuildArch = $(if ($env:LWRCLPY_WINDOWS_BUILD_ARCH) { $env:LWRCLPY_WINDOWS_BUILD_ARCH } else { "x64" }),
    [string]$PackageVersion = $(if ($env:PKG_VERSION) { $env:PKG_VERSION.TrimStart("v") } else { "" })
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "build_env.ps1")
$BuildArch = Normalize-WindowsBuildArch $BuildArch

function Write-Utf8NoBom($Path, $Value) {
    $dir = Split-Path $Path -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Normalize-PythonFilesNoBom($Root) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    Get-ChildItem -Path $Root -Recurse -File -Include "*.py" | ForEach-Object {
        $text = [System.IO.File]::ReadAllText($_.FullName)
        $text = $text.Replace([string][char]0xFEFF, "")
        [System.IO.File]::WriteAllText($_.FullName, $text, $encoding)
    }
}

function Patch-FastDdsInit($FastDdsPackageDir) {
    $init = Join-Path $FastDdsPackageDir "__init__.py"
    if (-not (Test-Path $init)) {
        return
    }
    $text = Get-Content $init -Raw
    $old = "if __import__('os').name == 'nt': import win32api; win32api.LoadLibrary('fastdds-3.6.dll')"
    if (-not $text.Contains($old)) {
        return
    }
    $new = @'
if __import__('os').name == 'nt':
    import os as _fastdds_os, ctypes as _fastdds_ctypes
    for _fastdds_dir in (
        _fastdds_os.path.abspath(_fastdds_os.path.join(_fastdds_os.path.dirname(__file__), '..', 'lwrclpy', '_vendor', 'lib')),
        _fastdds_os.path.abspath(_fastdds_os.path.join(_fastdds_os.path.dirname(__file__), '..', 'lib')),
    ):
        if _fastdds_os.path.isdir(_fastdds_dir):
            try:
                _fastdds_os.add_dll_directory(_fastdds_dir)
            except Exception:
                pass
            _fastdds_dll = _fastdds_os.path.join(_fastdds_dir, 'fastdds-3.6.dll')
            if _fastdds_os.path.exists(_fastdds_dll):
                _fastdds_ctypes.WinDLL(_fastdds_dll)
                break
'@
    $text = $text.Replace($old, $new.TrimEnd())
    Write-Utf8NoBom $init $text
}

function Find-Dumpbin {
    $cmd = Get-Command dumpbin.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $requiredComponent = Get-VsRequiredComponent $BuildArch
        $installPath = & $vswhere -latest -products * -requires $requiredComponent -property installationPath
        if (-not $installPath -and $BuildArch -eq "arm64") {
            $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        }
        if ($installPath) {
            $toolArch = $(if ($BuildArch -eq "arm64") { "arm64" } else { "x64" })
            $candidate = Get-ChildItem -Path (Join-Path $installPath "VC\Tools\MSVC") -Recurse -Filter dumpbin.exe -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match "\\bin\\Host$toolArch\\$toolArch\\dumpbin.exe$" } |
                Sort-Object FullName -Descending |
                Select-Object -First 1
            if ($candidate) {
                return $candidate.FullName
            }
        }
    }
    return $null
}

function Get-DllDependents($Dumpbin, $DllPath) {
    $out = & $Dumpbin /DEPENDENTS $DllPath 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "dumpbin failed for $DllPath"
    }
    $deps = New-Object System.Collections.Generic.List[string]
    foreach ($line in $out) {
        $name = $line.Trim()
        if ($name -match '^[A-Za-z0-9_.+-]+\.dll$') {
            $deps.Add($name)
        }
    }
    return $deps
}

function Get-RelativePathForPython($Root, $Path) {
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path $Path is not under $Root"
    }
    return $pathFull.Substring($rootFull.Length).Replace('\', '/')
}

function Build-GeneratedDllDependencyMap($Root) {
    $dumpbin = Find-Dumpbin
    if (-not $dumpbin) {
        throw "dumpbin.exe not found; run from a Visual Studio developer environment"
    }
    Write-Host "[INFO] Resolving generated DLL dependencies with $dumpbin"

    $dlls = Get-ChildItem -Path $Root -Recurse -File -Filter "*.dll" |
        Where-Object { $_.FullName -notmatch "\\lwrclpy\\_vendor\\" -and $_.FullName -notmatch "\\lwrclpy\.libs\\" }

    $byName = @{}
    foreach ($dll in $dlls) {
        $key = $dll.Name.ToLowerInvariant()
        if (-not $byName.ContainsKey($key)) {
            $byName[$key] = New-Object System.Collections.Generic.List[object]
        }
        $byName[$key].Add($dll)
    }

    $map = @{}
    foreach ($dll in $dlls) {
        $deps = New-Object System.Collections.Generic.List[string]
        $dllTopPackage = Get-RelativePathForPython $Root $dll.FullName
        $dllTopPackage = $dllTopPackage.Split('/')[0]
        foreach ($dep in (Get-DllDependents $dumpbin $dll.FullName)) {
            $key = $dep.ToLowerInvariant()
            if (-not $byName.ContainsKey($key)) {
                continue
            }
            $candidates = @($byName[$key].ToArray())
            $chosen = $null
            $samePackage = @($candidates | Where-Object { (Get-RelativePathForPython $Root $_.FullName).Split('/')[0] -eq $dllTopPackage })
            if ($samePackage.Count -eq 1) {
                $chosen = $samePackage[0]
            } elseif ($candidates.Count -eq 1) {
                $chosen = $candidates[0]
            }
            if ($chosen) {
                $deps.Add((Get-RelativePathForPython $Root $chosen.FullName))
            } else {
                Write-Warning "Ambiguous generated DLL dependency $dep for $($dll.FullName); relying on Windows loader search path"
            }
        }
        $map[$dll.FullName.ToLowerInvariant()] = @($deps | Sort-Object -Unique)
    }
    return $map
}

function Patch-GeneratedDllLoaders($Root) {
    $dependencyMap = Build-GeneratedDllDependencyMap $Root
    $pattern = "if __import__\('os'\)\.name == 'nt': import win32api; win32api\.LoadLibrary\('([^']+\.dll)'\)"
    Get-ChildItem -Path $Root -Recurse -File -Include "*.py" | ForEach-Object {
        $pyFile = $_
        $text = [System.IO.File]::ReadAllText($pyFile.FullName)
        if ($text -notmatch $pattern) {
            return
        }
        $patched = [regex]::Replace($text, $pattern, {
            param($m)
            $dllName = $m.Groups[1].Value.ToLowerInvariant()
            $dllPath = Join-Path $pyFile.DirectoryName $dllName
            $deps = @()
            $key = [System.IO.Path]::GetFullPath($dllPath).ToLowerInvariant()
            if ($dependencyMap.ContainsKey($key)) {
                $deps = @($dependencyMap[$key])
            }
            $depLiteral = "[" + (($deps | ForEach-Object { "'" + $_.Replace("'", "\\'") + "'" }) -join ", ") + "]"
            "if __import__('os').name == 'nt': from lwrclpy._bootstrap_fastdds import ensure_fastdds as _fastdds_ensure, preload_generated_dlls as _fastdds_preload; _fastdds_ensure(); _fastdds_preload($depLiteral); import os as _fastdds_os, ctypes as _fastdds_ctypes; _fastdds_dir = _fastdds_os.path.dirname(__file__); globals().setdefault('_fastdds_dll_dirs', []).append(_fastdds_os.add_dll_directory(_fastdds_dir)); _fastdds_ctypes.WinDLL(_fastdds_os.path.join(_fastdds_dir, '$dllName'))"
        })
        Write-Utf8NoBom $pyFile.FullName $patched
    }
}

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

function Test-ValidAuthenticodeSignature($Path) {
    $signature = Get-AuthenticodeSignature -FilePath $Path
    return $signature.Status -eq "Valid"
}

function Get-PythonOpenSslDllRoots {
    $rootsJson = python -c "import json, os, sys, sysconfig; roots=[sys.base_prefix, sys.prefix, os.path.dirname(sys.executable), sysconfig.get_config_var('BINDIR')]; print(json.dumps([r for r in dict.fromkeys(roots) if r]))"
    if ($LASTEXITCODE -ne 0 -or -not $rootsJson) {
        throw "Unable to query Python runtime paths for signed OpenSSL DLLs"
    }

    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($root in @($rootsJson | ConvertFrom-Json)) {
        if ($root) {
            $roots.Add($root)
        }
    }

    if ($env:RUNNER_TOOL_CACHE) {
        $pythonToolCache = Join-Path $env:RUNNER_TOOL_CACHE "Python"
        if (Test-Path $pythonToolCache) {
            Get-ChildItem -Path $pythonToolCache -Filter "python.exe" -File -Recurse -ErrorAction SilentlyContinue |
                ForEach-Object { $roots.Add($_.DirectoryName) }
        }
    }

    $expanded = New-Object System.Collections.Generic.List[string]
    foreach ($root in $roots.ToArray()) {
        if (-not $root) {
            continue
        }
        $expanded.Add($root)
        $expanded.Add((Join-Path $root "DLLs"))
        $expanded.Add((Join-Path $root "Library\bin"))
    }
    return @($expanded.ToArray() | Where-Object { Test-Path $_ } | Select-Object -Unique)
}

function Get-OpenSslDllAbiToken($Name) {
    if ($Name -match '^lib(?:ssl|crypto)-([^-]+)(?:-.*)?\.dll$') {
        return $Matches[1]
    }
    return ""
}

function Get-OpenSslDllArchitectureToken($Name) {
    if ($Name -match '-(x64|arm64)\.dll$') {
        return $Matches[1]
    }
    return ""
}

function Get-SignedPythonOpenSslDlls($Kind) {
    $matches = New-Object System.Collections.Generic.List[object]
    foreach ($root in (Get-PythonOpenSslDllRoots)) {
        Get-ChildItem -Path $root -Filter "lib$Kind*.dll" -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                if (Test-ValidAuthenticodeSignature $_.FullName) {
                    $matches.Add($_)
                }
            }
    }

    $unique = @($matches.ToArray() | Sort-Object FullName -Unique)
    if ($unique.Count -eq 0) {
        throw "Signed Python lib$Kind DLL was not found. Refusing to package unsigned OpenSSL runtime DLLs."
    }
    return $unique
}

function Select-SignedPythonOpenSslDll($Kind, $ExpectedName) {
    $unique = @(Get-SignedPythonOpenSslDlls $Kind)
    $exact = @($unique | Where-Object { $_.Name -ieq $ExpectedName })
    if ($exact.Count -gt 0) {
        if ($exact.Count -gt 1) {
            Write-Host "[INFO] Multiple exact signed Python lib$Kind DLLs found; using $($exact[0].FullName)"
        }
        return $exact[0]
    }

    $expectedAbi = Get-OpenSslDllAbiToken $ExpectedName
    $expectedArch = Get-OpenSslDllArchitectureToken $ExpectedName
    if ($expectedAbi) {
        $compatible = @($unique | Where-Object { (Get-OpenSslDllAbiToken $_.Name) -eq $expectedAbi })
        if ($expectedArch) {
            $compatible = @($compatible | Where-Object { (Get-OpenSslDllArchitectureToken $_.Name) -eq $expectedArch })
        }
        if ($compatible.Count -eq 0) {
            $available = (($unique | ForEach-Object { $_.Name }) -join ", ")
            throw "No signed Python lib$Kind DLL matches expected OpenSSL ABI '$expectedAbi' and architecture '$expectedArch' for $ExpectedName. Available signed DLLs: $available"
        }
        $unique = $compatible
    }

    if ($unique.Count -gt 1) {
        Write-Host "[INFO] Multiple signed Python lib$Kind DLLs found; using $($unique[0].FullName)"
    }
    return $unique[0]
}

function Get-ExpectedOpenSslDllNames($DllRoots, $Kind, $FallbackName) {
    $names = New-Object System.Collections.Generic.List[string]
    foreach ($root in $DllRoots) {
        Get-ChildItem -Path $root -Filter "lib$Kind*.dll" -File -ErrorAction SilentlyContinue |
            ForEach-Object { $names.Add($_.Name) }
    }

    $unique = @($names.ToArray() | Sort-Object -Unique)
    if ($unique.Count -eq 0) {
        return @($FallbackName)
    }
    return $unique
}

function Copy-SignedPythonOpenSslDlls($Destination, $DllRoots) {
    foreach ($kind in @("ssl", "crypto")) {
        $fallback = @(Get-SignedPythonOpenSslDlls $kind)[0].Name
        foreach ($name in (Get-ExpectedOpenSslDllNames $DllRoots $kind $fallback)) {
            $source = Select-SignedPythonOpenSslDll $kind $name
            $target = Join-Path $Destination $name
            Copy-Item $source.FullName $target -Force
            if (-not (Test-ValidAuthenticodeSignature $target)) {
                throw "Copied OpenSSL DLL is not Authenticode-valid: $target"
            }
            Write-Host "[INFO] Vendored signed Python OpenSSL DLL: $($source.Name) -> $name"
        }
    }
}

function Remove-StagedOpenSslDllsOutsideVendor($Root, $VendorLib) {
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $vendorFull = [System.IO.Path]::GetFullPath($VendorLib).TrimEnd('\') + '\'
    if (-not $vendorFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Vendor library path $VendorLib is not under staging root $Root"
    }

    Get-ChildItem -Path $Root -Recurse -File -Include "libssl*.dll", "libcrypto*.dll" |
        Where-Object {
            -not ([System.IO.Path]::GetFullPath($_.FullName).StartsWith($vendorFull, [System.StringComparison]::OrdinalIgnoreCase))
        } |
        ForEach-Object {
            Write-Host "[INFO] Removing non-vendored OpenSSL DLL from staged wheel tree: $($_.FullName)"
            Remove-Item -LiteralPath $_.FullName -Force
        }
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
Write-Host "[INFO] build arch: $BuildArch"

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
    "patch_message_setter_compat.py",
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
$thirdPartyNotices = Join-Path $repoRoot "THIRD_PARTY_NOTICES.md"
if (Test-Path $thirdPartyNotices) {
    Copy-Item $thirdPartyNotices (Join-Path $stagingRoot "rclpy\THIRD_PARTY_NOTICES.md") -Force
}
Copy-Tree (Join-Path $repoRoot "tf2_py") (Join-Path $stagingRoot "tf2_py")
Copy-Tree (Join-Path $repoRoot "tf2_ros") (Join-Path $stagingRoot "tf2_ros")
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

$patterns = @("*fastdds*.dll", "*fastcdr*.dll", "*foonathan*.dll", "*tinyxml2*.dll", "zlib*.dll")
foreach ($root in $dllRoots) {
    foreach ($pattern in $patterns) {
        Get-ChildItem -Path $root -Filter $pattern -File -ErrorAction SilentlyContinue |
            ForEach-Object { Copy-Item $_.FullName (Join-Path $vendorLib $_.Name) -Force }
    }
}
Copy-SignedPythonOpenSslDlls $vendorLib $dllRoots
Remove-StagedOpenSslDllsOutsideVendor $stagingRoot $vendorLib
Patch-FastDdsInit $vendorFastdds
Patch-FastDdsInit (Join-Path $stagingRoot "fastdds")

$bootstrap = @'
import os, sys, ctypes

_pkg_dir = os.path.dirname(__file__)
_vendor_parent = os.path.join(_pkg_dir, "_vendor")
_vendor_lib = os.path.join(_vendor_parent, "lib")
_site_root = os.path.dirname(_pkg_dir)
_dll_dir_handles = []
_did_scan_dll_dirs = False
_loaded_generated_dlls = set()

def _add_dll_dir(path):
    if os.path.isdir(path):
        try:
            _dll_dir_handles.append(os.add_dll_directory(path))
        except Exception:
            pass

def _add_generated_type_dirs():
    global _did_scan_dll_dirs
    if _did_scan_dll_dirs:
        return
    _did_scan_dll_dirs = True
    for root, _dirs, files in os.walk(_site_root):
        if any(name.lower().endswith(".dll") for name in files):
            _add_dll_dir(root)

def preload_generated_dlls(relative_paths):
    for relative_path in relative_paths:
        path = os.path.normpath(os.path.join(_site_root, relative_path))
        if path in _loaded_generated_dlls:
            continue
        if os.path.exists(path):
            ctypes.WinDLL(path)
            _loaded_generated_dlls.add(path)

def ensure_fastdds():
    _add_dll_dir(_vendor_lib)
    _add_generated_type_dirs()
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
Write-Utf8NoBom (Join-Path $stagingRoot "lwrclpy\_bootstrap_fastdds.py") $bootstrap

$init = Join-Path $stagingRoot "lwrclpy\__init__.py"
if (-not (Test-Path $init)) {
    Write-Utf8NoBom $init "# auto-generated`n"
}
$initContent = Get-Content $init -Raw
if (-not $initContent.Contains("ensure_fastdds()")) {
    $prefix = "from ._bootstrap_fastdds import ensure_fastdds`nensure_fastdds()`n"
    Write-Utf8NoBom $init ($prefix + $initContent)
}

@"
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta:__legacy__"
"@ | ForEach-Object { Write-Utf8NoBom (Join-Path $stagingRoot "pyproject.toml") $_ }

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
install_requires =
    pywin32
include_package_data = True
zip_safe = False

[options.package_data]
* = **/*.py, **/*.pyd, **/*.dll, **/*Wrapper.*, **/LICENSE, **/*.md
"@ | ForEach-Object { Write-Utf8NoBom (Join-Path $stagingRoot "setup.cfg") $_ }

@'
from setuptools import setup
from setuptools.dist import Distribution

class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True

if __name__ == "__main__":
    setup(distclass=BinaryDistribution)
'@ | ForEach-Object { Write-Utf8NoBom (Join-Path $stagingRoot "setup.py") $_ }

Patch-GeneratedDllLoaders $stagingRoot
Normalize-PythonFilesNoBom $stagingRoot

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
python -m delvewheel repair $wheel.FullName -w $wheelhouse --add-path $vendorLib --ignore-existing
if ($LASTEXITCODE -ne 0) {
    throw "delvewheel repair failed"
}

Write-Host "[OK] Windows wheel ready under $wheelhouse"
Get-ChildItem $wheelhouse -Filter "$pkgName-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
