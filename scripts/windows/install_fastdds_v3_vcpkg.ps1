param(
    [string]$Prefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { "C:\fast-dds-v3" }),
    [string]$GenPrefix = $(if ($env:FASTDDSGEN_PREFIX) { $env:FASTDDSGEN_PREFIX } else { "C:\fast-dds-gen-v3" }),
    [string]$Workspace = $(if ($env:FASTDDS_WS) { $env:FASTDDS_WS } else { Join-Path $env:USERPROFILE "fastdds_python_ws" }),
    [string]$ReposRef = $(if ($env:FASTDDS_PYTHON_REPOS_REF) { $env:FASTDDS_PYTHON_REPOS_REF } else { "v2.6.1" }),
    [string]$FastDdsGenRef = $(if ($env:FASTDDSGEN_REF) { $env:FASTDDSGEN_REF } else { "master" }),
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

function Invoke-Step($Message, [scriptblock]$Block) {
    Write-Host "[INFO] $Message"
    & $Block
}

function Ensure-Vcpkg($Root) {
    $exe = Join-Path $Root "vcpkg.exe"
    if (Test-Path $exe) {
        return $exe
    }

    if (-not (Test-Path $Root)) {
        Invoke-Step "Cloning vcpkg to $Root" {
            git clone https://github.com/microsoft/vcpkg.git $Root
        }
    }

    $bootstrap = Join-Path $Root "bootstrap-vcpkg.bat"
    if (-not (Test-Path $bootstrap)) {
        throw "vcpkg bootstrap script not found: $bootstrap"
    }
    Invoke-Step "Bootstrapping vcpkg" {
        & $bootstrap -disableMetrics
        if ($LASTEXITCODE -ne 0) {
            throw "vcpkg bootstrap failed"
        }
    }
    if (-not (Test-Path $exe)) {
        throw "vcpkg.exe was not created under $Root"
    }
    return $exe
}

function Install-VcpkgPackages($VcpkgExe, $Triplet) {
    Invoke-Step "Installing vcpkg Fast DDS for $Triplet" {
        & $VcpkgExe install "fastdds:$Triplet"
        if ($LASTEXITCODE -ne 0) {
            throw "vcpkg install fastdds failed"
        }
    }
}

function Clone-Ref($Url, $Ref, $Destination, $Name) {
    git clone --depth 1 --branch $Ref $Url $Destination
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Remove-Item $Destination -Recurse -Force -ErrorAction SilentlyContinue
    git clone $Url $Destination
    if ($LASTEXITCODE -ne 0) {
        throw "$Name clone failed"
    }
    Push-Location $Destination
    git checkout $Ref
    if ($LASTEXITCODE -ne 0) {
        throw "$Name checkout failed: $Ref"
    }
    Pop-Location
}

Require-Command git
Require-Command cmake
Require-Command python

if (-not (Get-Command swig -ErrorAction SilentlyContinue)) {
    Invoke-Step "Installing SWIG 4.1.1 for Fast-DDS-python compatibility" {
        python -m pip install --upgrade "swig==4.1.1"
    }
}
if (-not (Get-Command swig -ErrorAction SilentlyContinue)) {
    throw "SWIG is required, but swig==4.1.1 was not found after pip install"
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "Java 17+ is required. Install it first, for example: choco install openjdk17 -y"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRoot = $repoRoot.Path
$srcDir = Join-Path $Workspace "src"
$vcpkgExe = Ensure-Vcpkg $VcpkgRoot
Install-VcpkgPackages $vcpkgExe $VcpkgTriplet
$vcpkgInstalled = Join-Path $VcpkgRoot "installed\$VcpkgTriplet"
$vcpkgToolchain = Join-Path $VcpkgRoot "scripts\buildsystems\vcpkg.cmake"
if (-not (Test-Path $vcpkgToolchain)) {
    throw "vcpkg toolchain file not found: $vcpkgToolchain"
}

Invoke-Step "Preparing workspace at $Workspace" {
    if (Test-Path $Workspace) {
        Remove-Item $Workspace -Recurse -Force
    }
    New-Item -ItemType Directory -Path $srcDir -Force | Out-Null
    New-Item -ItemType Directory -Path $Prefix -Force | Out-Null
    New-Item -ItemType Directory -Path $GenPrefix -Force | Out-Null
}

Invoke-Step "Installing Python build tools" {
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install --upgrade colcon-common-extensions empy
}

Invoke-Step "Cloning Fast-DDS-python ($ReposRef)" {
    Clone-Ref "https://github.com/eProsima/Fast-DDS-python.git" $ReposRef (Join-Path $srcDir "Fast-DDS-python") "Fast-DDS-python"
}

Invoke-Step "Cloning Fast-DDS-Gen ($FastDdsGenRef)" {
    Clone-Ref "https://github.com/eProsima/Fast-DDS-Gen.git" $FastDdsGenRef (Join-Path $srcDir "Fast-DDS-Gen") "Fast-DDS-Gen"
}

$loanPatch = Join-Path $repoRoot "scripts\patch_fastdds_python_loan_helpers.py"
if (Test-Path $loanPatch) {
    Invoke-Step "Patching Fast-DDS-python loan helpers" {
        python $loanPatch $srcDir
    }
}

$genSrc = Join-Path $srcDir "Fast-DDS-Gen"
Invoke-Step "Building fastddsgen from $genSrc" {
    Push-Location $genSrc
    if (Test-Path ".\gradlew.bat") {
        .\gradlew.bat --no-daemon clean assemble
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen assemble failed" }
        .\gradlew.bat --no-daemon install --install_path="$GenPrefix"
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen install failed" }
    } else {
        .\gradlew --no-daemon clean assemble
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen assemble failed" }
        .\gradlew --no-daemon install --install_path="$GenPrefix"
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen install failed" }
    }
    Pop-Location
}

$fastddsgen = Join-Path $GenPrefix "bin\fastddsgen.bat"
if (-not (Test-Path $fastddsgen)) {
    $fastddsgen = Join-Path $GenPrefix "bin\fastddsgen"
}
if (-not (Test-Path $fastddsgen)) {
    throw "fastddsgen launcher was not installed under $GenPrefix\bin"
}

Invoke-Step "Probing fastddsgen -python" {
    $probe = Join-Path $Workspace "_probe"
    $out = Join-Path $probe "out"
    New-Item -ItemType Directory -Path $out -Force | Out-Null
    "module probe { struct Foo { long x; }; };" | Set-Content -Path (Join-Path $probe "Probe.idl") -Encoding ASCII
    & $fastddsgen -python -d $out -I $probe -replace (Join-Path $probe "Probe.idl")
    if ($LASTEXITCODE -ne 0 -or -not (Get-ChildItem $out -Filter "*.i" -Recurse -ErrorAction SilentlyContinue)) {
        throw "fastddsgen -python probe failed"
    }
}

$swig = (Get-Command swig).Source
$py = (Get-Command python).Source
$env:CMAKE_BUILD_PARALLEL_LEVEL = "$Jobs"
$env:CMAKE_GENERATOR = "Ninja"
$env:VCPKG_ROOT = "$VcpkgRoot"
$env:VCPKG_DEFAULT_TRIPLET = "$VcpkgTriplet"
$env:CMAKE_PREFIX_PATH = "$Prefix;$vcpkgInstalled;$env:CMAKE_PREFIX_PATH"
$env:PATH = "$vcpkgInstalled\bin;$vcpkgInstalled\debug\bin;$Prefix\bin;$Prefix\lib;$GenPrefix\bin;$env:PATH"

$cmakeArgs = @(
    "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_INSTALL_PREFIX=$Prefix",
    "-DCMAKE_TOOLCHAIN_FILE=$vcpkgToolchain",
    "-DVCPKG_TARGET_TRIPLET=$VcpkgTriplet",
    "-DPython3_EXECUTABLE=$py",
    "-DSWIG_EXECUTABLE=$swig",
    "-DCMAKE_PREFIX_PATH=$Prefix;$vcpkgInstalled"
)

Invoke-Step "Building fastdds_python against vcpkg Fast DDS" {
    Push-Location $Workspace
    colcon build `
        --base-paths (Join-Path $srcDir "Fast-DDS-python\fastdds_python") `
        --merge-install `
        --install-base "$Prefix" `
        --cmake-args @cmakeArgs `
        --event-handlers console_cohesion+ status+ `
        --executor sequential `
        --parallel-workers $Jobs
    Pop-Location
}

Write-Host ""
Write-Host "[OK] Windows Fast DDS Python installation completed"
Write-Host "  FASTDDS_PREFIX=$Prefix"
Write-Host "  FASTDDSGEN_BIN=$fastddsgen"
Write-Host "  VCPKG_ROOT=$VcpkgRoot"
Write-Host "  VCPKG_DEFAULT_TRIPLET=$VcpkgTriplet"
Write-Host "  VCPKG_FASTDDS=$vcpkgInstalled"
Write-Host ""
Write-Host "Sanity check:"
Write-Host "  `$env:PATH = `"$vcpkgInstalled\bin;$Prefix\bin;$Prefix\lib;$GenPrefix\bin;`$env:PATH`""
Write-Host "  python -c `"import fastdds; print('fastdds OK')`""
