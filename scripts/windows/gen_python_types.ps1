param(
    [string]$Prefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { "C:\fast-dds-v3" }),
    [string]$FastddsgenBin = $(if ($env:FASTDDSGEN_BIN) { $env:FASTDDSGEN_BIN } else { "C:\fast-dds-gen-v3\bin\fastddsgen.bat" }),
    [string]$RosTypesRoot = $(if ($env:ROS_TYPES_ROOT) { $env:ROS_TYPES_ROOT } else { (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "third_party\ros-data-types-for-fastdds") }),
    [string]$BuildRoot = $(if ($env:BUILD_ROOT) { $env:BUILD_ROOT } else { (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "._types_python_build_v3") }),
    [string]$Filter = $(if ($env:FILTER) { $env:FILTER } else { "" }),
    [string]$VcpkgRoot = $(if ($env:VCPKG_ROOT) { $env:VCPKG_ROOT } elseif ($env:VCPKG_INSTALLATION_ROOT) { $env:VCPKG_INSTALLATION_ROOT } else { "C:\vcpkg" }),
    [string]$VcpkgTriplet = $(if ($env:VCPKG_DEFAULT_TRIPLET) { $env:VCPKG_DEFAULT_TRIPLET } else { "x64-windows" }),
    [int]$Jobs = $(if ($env:JOBS) { [int]$env:JOBS } else { [Environment]::ProcessorCount })
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' not found"
    }
}

function Find-CMakePackageDir($Roots, $PackageName) {
    foreach ($root in $Roots) {
        if (-not $root -or -not (Test-Path $root)) {
            continue
        }
        $candidates = @(
            (Join-Path $root "share\$PackageName\cmake\$PackageName-config.cmake"),
            (Join-Path $root "lib\cmake\$PackageName\$PackageName-config.cmake"),
            (Join-Path $root "CMake\$PackageName\$PackageName-config.cmake")
        )
        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) {
                return (Split-Path $candidate -Parent)
            }
        }
        $found = Get-ChildItem -Path $root -Filter "$PackageName-config.cmake" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            return $found.Directory.FullName
        }
    }
    throw "$PackageName-config.cmake not found under: $($Roots -join ', ')"
}

function Copy-DirectoryMirror($Source, $Destination) {
    if (Test-Path $Destination) {
        Remove-Item $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Copy-Item (Join-Path $Source "*") $Destination -Recurse -Force
}

function Patch-CMakeLists($Dir, $DirRel, $IncStageRoot) {
    $cml = Join-Path $Dir "CMakeLists.txt"
    if (-not (Test-Path $cml)) {
        return
    }
    $text = Get-Content $cml -Raw
    if ($text.Contains("__FASTDDS_INC_STAGE_ADDED__")) {
        return
    }
    $prefix = @"
# __FASTDDS_INC_STAGE_ADDED__
set(FASTDDS_GEN_INCLUDE_STAGE "$($IncStageRoot -replace '\\','/')") 
include_directories("`${FASTDDS_GEN_INCLUDE_STAGE}")
set(CMAKE_SWIG_FLAGS `${CMAKE_SWIG_FLAGS} "-I`${FASTDDS_GEN_INCLUDE_STAGE}")
set(SWIG_INCLUDE_DIRS "`${SWIG_INCLUDE_DIRS};`${FASTDDS_GEN_INCLUDE_STAGE}")
# __FASTDDS_SUBINC_ADDED__
include_directories("$((Join-Path $IncStageRoot $DirRel) -replace '\\','/')")
set(CMAKE_SWIG_FLAGS `${CMAKE_SWIG_FLAGS} "-I$((Join-Path $IncStageRoot $DirRel) -replace '\\','/')")
set(SWIG_INCLUDE_DIRS "`${SWIG_INCLUDE_DIRS};$((Join-Path $IncStageRoot $DirRel) -replace '\\','/')")
"@
    Set-Content -Path $cml -Value ($prefix + "`n" + $text) -Encoding UTF8
}

Require-Command cmake
Require-Command swig
Require-Command python
Require-Command java

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRoot = $repoRoot.Path
$patchPy = Join-Path $repoRoot "scripts\patch_fastdds_swig_v3.py"
if (-not (Test-Path $patchPy)) {
    throw "Patch script missing: $patchPy"
}
if (-not (Test-Path (Join-Path $RosTypesRoot "src"))) {
    throw "ROS_TYPES_ROOT/src not found: $RosTypesRoot\src"
}
if (-not (Test-Path $FastddsgenBin)) {
    throw "fastddsgen not found: $FastddsgenBin"
}

$genSrcRoot = Join-Path $BuildRoot "src"
$incStageRoot = Join-Path $BuildRoot "include\src"
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $incStageRoot -Force | Out-Null

Write-Host "[INFO] Mirroring IDL tree to $genSrcRoot"
Copy-DirectoryMirror (Join-Path $RosTypesRoot "src") $genSrcRoot

Get-ChildItem -Path $genSrcRoot -Filter "CMakeLists.txt" -Recurse -File |
    Where-Object {
        $parts = $_.FullName.Substring($genSrcRoot.Length).TrimStart([char[]]@("\", "/")) -split "[\\/]"
        $parts.Length -eq 3
    } |
    ForEach-Object { Rename-Item $_.FullName ($_.FullName + ".upstream") -Force }

$vcpkgInstalled = Join-Path $VcpkgRoot "installed\$VcpkgTriplet"
$vcpkgToolchain = Join-Path $VcpkgRoot "scripts\buildsystems\vcpkg.cmake"
if (-not (Test-Path $vcpkgToolchain)) {
    throw "vcpkg toolchain file not found: $vcpkgToolchain"
}
$cmakePackageRoots = @($Prefix, $vcpkgInstalled)
$fastddsDir = Find-CMakePackageDir $cmakePackageRoots "fastdds"
$fastcdrDir = Find-CMakePackageDir $cmakePackageRoots "fastcdr"
Write-Host "[INFO] fastdds_DIR=$fastddsDir"
Write-Host "[INFO] fastcdr_DIR=$fastcdrDir"
Write-Host "[INFO] vcpkg toolchain=$vcpkgToolchain"

if (Test-Path (Join-Path $genSrcRoot "gazebo_msgs")) {
    Get-ChildItem -Path (Join-Path $genSrcRoot "gazebo_msgs") -Filter "*.idl" -Recurse -File |
        ForEach-Object {
            $text = Get-Content $_.FullName -Raw
            $text = $text -replace '(^|[^A-Za-z0-9_])FIXED([^A-Za-z0-9_])', '${1}_FIXED${2}'
            Set-Content -Path $_.FullName -Value $text -Encoding UTF8
        }
}

$idls = Get-ChildItem -Path $genSrcRoot -Filter "*.idl" -Recurse -File |
    ForEach-Object { $_.FullName.Substring($genSrcRoot.Length).TrimStart([char[]]@("\", "/")) } |
    Sort-Object
if ($Filter) {
    $idls = $idls | Where-Object { $_ -match $Filter }
}
if (-not $idls) {
    throw "No IDL files found"
}

$failedGen = New-Object System.Collections.Generic.List[string]
foreach ($rel in $idls) {
    $idlPath = Join-Path $genSrcRoot $rel
    $dirRel = Split-Path $rel -Parent
    $base = [System.IO.Path]::GetFileNameWithoutExtension($rel)
    $outDir = Join-Path (Join-Path $genSrcRoot $dirRel) $base
    if (Test-Path $outDir) {
        Remove-Item $outDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null

    Write-Host "[GEN] $rel"
    & $FastddsgenBin -python -cs -typeros2 -language c++ -d $outDir -I $genSrcRoot -replace $idlPath *> (Join-Path $outDir "_gen.log")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $outDir "$base.i"))) {
        Write-Host "[ERR] fastddsgen failed: $rel"
        $failedGen.Add($rel)
        continue
    }

    python $patchPy (Join-Path $outDir "$base.i")
    $iface = Get-Content (Join-Path $outDir "$base.i") -Raw
    if (-not $iface.Contains("__FASTDDS_V3_CPP_BLOCK__")) {
        Write-Host "[ERR] $base.i missing Fast DDS v3 patch marker"
        $failedGen.Add($rel)
        continue
    }

    $incDst = Join-Path $incStageRoot $dirRel
    New-Item -ItemType Directory -Path $incDst -Force | Out-Null
    Get-ChildItem -Path $outDir -File |
        Where-Object { $_.Extension -in @(".i", ".hpp") -or $_.Name -like "*TypeObjectSupport.*" -or $_.Name -like "*PubSubTypes.*" } |
        ForEach-Object { Copy-Item $_.FullName (Join-Path $incDst $_.Name) -Force }

    Patch-CMakeLists $outDir $dirRel $incStageRoot
}

if ($failedGen.Count -gt 0) {
    Write-Host "[WARN] fastddsgen failed on $($failedGen.Count) file(s)"
    $failedGen | ForEach-Object { Write-Host " - $_" }
}

$swig = (Get-Command swig).Source
$py = (Get-Command python).Source
$env:VCPKG_ROOT = "$VcpkgRoot"
$env:VCPKG_DEFAULT_TRIPLET = "$VcpkgTriplet"
$env:PATH = "$vcpkgInstalled\bin;$vcpkgInstalled\debug\bin;$Prefix\bin;$Prefix\lib;$env:PATH"
$env:CMAKE_PREFIX_PATH = "$Prefix;$vcpkgInstalled;$env:CMAKE_PREFIX_PATH"
$env:CMAKE_BUILD_PARALLEL_LEVEL = "$Jobs"

$outDirs = Get-ChildItem -Path $genSrcRoot -Filter "CMakeLists.txt" -Recurse -File |
    Where-Object {
        $parts = $_.FullName.Substring($genSrcRoot.Length).TrimStart([char[]]@("\", "/")) -split "[\\/]"
        $parts.Length -eq 4
    } |
    ForEach-Object { $_.Directory.FullName } |
    Sort-Object -Unique

$failedBuild = New-Object System.Collections.Generic.List[string]
foreach ($dir in $outDirs) {
    Write-Host "[CMAKE] $($dir.Substring($BuildRoot.Length).TrimStart([char[]]@('\','/')))"
    $build = Join-Path $dir "build"
    New-Item -ItemType Directory -Path $build -Force | Out-Null
    Push-Location $build
    cmake .. `
        -G Ninja `
        -DCMAKE_BUILD_TYPE=Release `
        -DCMAKE_CXX_STANDARD=17 `
        -DCMAKE_TOOLCHAIN_FILE="$vcpkgToolchain" `
        -DVCPKG_TARGET_TRIPLET="$VcpkgTriplet" `
        -DCMAKE_PREFIX_PATH="$Prefix;$vcpkgInstalled" `
        -Dfastdds_DIR="$fastddsDir" `
        -Dfastcdr_DIR="$fastcdrDir" `
        -DPython3_EXECUTABLE="$py" `
        -DSWIG_EXECUTABLE="$swig" *> "_cmake_configure.log"
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        $failedBuild.Add("$dir (configure)")
        continue
    }
    cmake --build . --config Release --parallel $Jobs *> "_cmake_build.log"
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        $failedBuild.Add("$dir (build)")
        continue
    }
    Pop-Location
}

if ($failedBuild.Count -gt 0) {
    Write-Host "[ERR] Finished with build failures: $($failedBuild.Count)"
    $failedBuild | ForEach-Object { Write-Host " - $_" }
    exit 2
}

Write-Host "[OK] All generated type builds finished."
