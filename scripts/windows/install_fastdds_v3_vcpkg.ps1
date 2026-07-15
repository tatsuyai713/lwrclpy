param(
    [string]$BuildWorkRoot = $(if ($env:LWRCLPY_WINDOWS_BUILD_ROOT) { $env:LWRCLPY_WINDOWS_BUILD_ROOT } else { "C:\lwrclpy_windows_build" }),
    [string]$Prefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { (Join-Path $BuildWorkRoot "fastdds-prefix") }),
    [string]$GenPrefix = $(if ($env:FASTDDSGEN_PREFIX) { $env:FASTDDSGEN_PREFIX } else { (Join-Path $BuildWorkRoot "fastddsgen-prefix") }),
    [string]$Workspace = $(if ($env:FASTDDS_WS) { $env:FASTDDS_WS } else { (Join-Path $BuildWorkRoot "fastdds-workspace") }),
    [string]$ReposRef = $(if ($env:FASTDDS_PYTHON_REPOS_REF) { $env:FASTDDS_PYTHON_REPOS_REF } else { "v2.6.1" }),
    [string]$FastDdsGenRef = $(if ($env:FASTDDSGEN_REF) { $env:FASTDDSGEN_REF } else { "master" }),
    [string]$VcpkgRoot = $(if ($env:VCPKG_ROOT) { $env:VCPKG_ROOT } elseif ($env:VCPKG_INSTALLATION_ROOT) { $env:VCPKG_INSTALLATION_ROOT } else { (Join-Path $BuildWorkRoot "vcpkg") }),
    [string]$VcpkgTriplet = $(if ($env:VCPKG_DEFAULT_TRIPLET) { $env:VCPKG_DEFAULT_TRIPLET } else { "x64-windows" }),
    [string]$BuildArch = $(if ($env:LWRCLPY_WINDOWS_BUILD_ARCH) { $env:LWRCLPY_WINDOWS_BUILD_ARCH } else { "x64" }),
    [int]$Jobs = $(if ($env:JOBS) { [int]$env:JOBS } else { [Environment]::ProcessorCount })
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "build_env.ps1")
$BuildArch = Normalize-WindowsBuildArch $BuildArch
Initialize-WindowsBuildEnvironment $BuildArch

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

    $bootstrap = Join-Path $Root "bootstrap-vcpkg.bat"
    if (-not (Test-Path $Root) -or ((-not (Test-Path $bootstrap)) -and -not (Get-ChildItem -Path $Root -Force -ErrorAction SilentlyContinue))) {
        Invoke-Step "Cloning vcpkg to $Root" {
            git clone https://github.com/microsoft/vcpkg.git $Root | Out-Host
        }
    }

    if (-not (Test-Path $bootstrap)) {
        throw "vcpkg bootstrap script not found: $bootstrap"
    }
    Invoke-Step "Bootstrapping vcpkg" {
        & $bootstrap -disableMetrics | Out-Host
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
        $env:VCPKG_ROOT = (Split-Path $VcpkgExe -Parent)
        & $VcpkgExe install "fastdds:$Triplet"
        if ($LASTEXITCODE -ne 0) {
            throw "vcpkg install fastdds failed"
        }
    }
}

function Test-FastDdsCache {
    $fastddsgenBat = Join-Path $GenPrefix "bin\fastddsgen.bat"
    $fastddsgenExe = Join-Path $GenPrefix "bin\fastddsgen"
    if (-not (Test-Path $fastddsgenBat) -and -not (Test-Path $fastddsgenExe)) {
        return $false
    }
    if (-not (Test-Path (Join-Path $Prefix "bin\fastdds.dll")) -and
        -not (Test-Path (Join-Path $Prefix "lib\fastdds.dll"))) {
        return $false
    }
    if (-not (Get-ChildItem -Path $Prefix -Filter "_fastdds_python*.pyd" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        return $false
    }

    $oldPath = $env:PATH
    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PATH = "$vcpkgInstalled\bin;$vcpkgInstalled\debug\bin;$Prefix\bin;$Prefix\lib;$GenPrefix\bin;$oldPath"
        $pythonDirs = Get-ChildItem -Path $Prefix -Directory -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\site-packages$" } |
            ForEach-Object { $_.FullName }
        if ($pythonDirs) {
            $env:PYTHONPATH = (($pythonDirs -join ";") + ";" + $oldPythonPath)
        }
        python -c "import fastdds; print('[OK] cached fastdds Python binding available')"
        return $LASTEXITCODE -eq 0
    } finally {
        $env:PATH = $oldPath
        $env:PYTHONPATH = $oldPythonPath
    }
}

function Clone-Ref($Url, $Ref, $Destination, $Name) {
    git clone --depth 1 --branch $Ref $Url $Destination | Out-Host
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Remove-Item $Destination -Recurse -Force -ErrorAction SilentlyContinue
    git clone $Url $Destination | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$Name clone failed"
    }
    Push-Location $Destination
    git checkout $Ref | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$Name checkout failed: $Ref"
    }
    Pop-Location
}

function Patch-FastDdsPythonCMake($SourceDir) {
    $cml = Join-Path $SourceDir "CMakeLists.txt"
    if (-not (Test-Path $cml)) {
        throw "Fast-DDS-python CMakeLists.txt not found: $cml"
    }
    $text = Get-Content $cml -Raw
    if (-not $text.Contains("find_package(nlohmann_json CONFIG REQUIRED)")) {
        $text = $text -replace "find_package\(fastdds 3 REQUIRED\)", "find_package(nlohmann_json CONFIG REQUIRED)`r`nfind_package(fastdds 3 REQUIRED)"
        Set-Content -Path $cml -Value $text -Encoding UTF8
    }
}

function Require-Java17ForGradle {
    if (-not (Use-JavaHome $env:JAVA_HOME)) {
        Add-JavaPath
    }

    $javaExe = Join-Path $env:JAVA_HOME "bin\java.exe"
    $major = Get-JavaMajorVersion $javaExe
    if ($major -lt 17) {
        throw "Fast-DDS-Gen requires Java 17 or newer, but JAVA_HOME=$env:JAVA_HOME resolves to Java $major"
    }

    $javaBin = Join-Path $env:JAVA_HOME "bin"
    $env:PATH = "$javaBin;$env:PATH"
    Write-Host "[INFO] Gradle JAVA_HOME=$env:JAVA_HOME"
    & $javaExe -version 2>&1 | Out-Host
    return "-Dorg.gradle.java.home=$env:JAVA_HOME"
}

Require-Command git
Require-Command cmake
Require-Command python

if (-not (Get-Command swig -ErrorAction SilentlyContinue)) {
    Invoke-Step "Installing SWIG 4.1.1 for Fast-DDS-python compatibility" {
        python -m pip install --upgrade "swig==4.1.1"
        if ($LASTEXITCODE -ne 0 -and (Get-Command choco -ErrorAction SilentlyContinue)) {
            Write-Host "[WARN] pip SWIG install failed; trying Chocolatey SWIG package"
            choco install swig -y --no-progress
        }
    }
    Add-PythonScriptsPath
}
if (-not (Get-Command swig -ErrorAction SilentlyContinue)) {
    throw "SWIG is required, but swig==4.1.1 was not found after pip install"
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "Java 17+ is required. Install it first, for example: choco install openjdk17 -y"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoRoot = $repoRoot.Path
$Prefix = [System.IO.Path]::GetFullPath($Prefix)
$GenPrefix = [System.IO.Path]::GetFullPath($GenPrefix)
$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$srcDir = Join-Path $Workspace "src"
$VcpkgRoot = [System.IO.Path]::GetFullPath($VcpkgRoot)
$env:VCPKG_ROOT = $VcpkgRoot
$env:VCPKG_DEFAULT_TRIPLET = $VcpkgTriplet
$vcpkgExe = Ensure-Vcpkg $VcpkgRoot
Install-VcpkgPackages $vcpkgExe $VcpkgTriplet
$vcpkgInstalled = Join-Path $VcpkgRoot "installed\$VcpkgTriplet"
$vcpkgToolchain = Join-Path $VcpkgRoot "scripts\buildsystems\vcpkg.cmake"
if (-not (Test-Path $vcpkgToolchain)) {
    throw "vcpkg toolchain file not found: $vcpkgToolchain"
}

if ($env:LWRCLPY_USE_FASTDDS_CACHE -eq "1" -and (Test-FastDdsCache)) {
    Write-Host "[INFO] Using cached Fast DDS installation at $Prefix"
    Write-Host "[INFO] Using cached Fast-DDS-Gen installation at $GenPrefix"
    return
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
$fastDdsPythonSrc = Join-Path $srcDir "Fast-DDS-python\fastdds_python"
Invoke-Step "Patching Fast-DDS-python CMake dependencies" {
    Patch-FastDdsPythonCMake $fastDdsPythonSrc
}

$genSrc = Join-Path $srcDir "Fast-DDS-Gen"
Invoke-Step "Building fastddsgen from $genSrc" {
    Push-Location $genSrc
    $gradleJavaHomeArg = Require-Java17ForGradle
    if (Test-Path ".\gradlew.bat") {
        .\gradlew.bat --no-daemon $gradleJavaHomeArg clean assemble
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen assemble failed" }
        .\gradlew.bat --no-daemon $gradleJavaHomeArg install --install_path="$GenPrefix"
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen install failed" }
    } else {
        .\gradlew --no-daemon $gradleJavaHomeArg clean assemble
        if ($LASTEXITCODE -ne 0) { throw "fastddsgen assemble failed" }
        .\gradlew --no-daemon $gradleJavaHomeArg install --install_path="$GenPrefix"
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
    $buildDir = Join-Path $Workspace "build\fastdds_python"
    if (Test-Path $buildDir) {
        Remove-Item $buildDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    Push-Location $buildDir
    cmake $fastDdsPythonSrc `
        -G Ninja `
        -DCMAKE_BUILD_TYPE=Release `
        -DCMAKE_INSTALL_PREFIX="$Prefix" `
        -DCMAKE_TOOLCHAIN_FILE="$vcpkgToolchain" `
        -DVCPKG_TARGET_TRIPLET="$VcpkgTriplet" `
        -DCMAKE_PREFIX_PATH="$Prefix;$vcpkgInstalled" `
        -DPython3_EXECUTABLE="$py" `
        -DSWIG_EXECUTABLE="$swig" `
        -Dnlohmann_json_DIR="$(Join-Path $vcpkgInstalled "share\nlohmann_json")"
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        throw "fastdds_python configure failed"
    }
    cmake --build . --config Release --parallel $Jobs
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        throw "fastdds_python build failed"
    }
    cmake --install . --config Release
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        throw "fastdds_python install failed"
    }
    Pop-Location
}

Write-Host ""
Write-Host "[OK] Windows Fast DDS Python installation completed"
Write-Host "  FASTDDS_PREFIX=$Prefix"
Write-Host "  FASTDDSGEN_BIN=$fastddsgen"
Write-Host "  LWRCLPY_WINDOWS_BUILD_ARCH=$BuildArch"
Write-Host "  VCPKG_ROOT=$VcpkgRoot"
Write-Host "  VCPKG_DEFAULT_TRIPLET=$VcpkgTriplet"
Write-Host "  VCPKG_FASTDDS=$vcpkgInstalled"
Write-Host ""
Write-Host "Sanity check:"
Write-Host "  `$env:PATH = `"$vcpkgInstalled\bin;$Prefix\bin;$Prefix\lib;$GenPrefix\bin;`$env:PATH`""
Write-Host "  python -c `"import fastdds; print('fastdds OK')`""
