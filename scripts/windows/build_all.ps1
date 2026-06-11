param(
    [string]$BuildWorkRoot = $(if ($env:LWRCLPY_WINDOWS_BUILD_ROOT) { $env:LWRCLPY_WINDOWS_BUILD_ROOT } else { "C:\lwrclpy_windows_build" }),
    [string]$Prefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { (Join-Path $BuildWorkRoot "fastdds-prefix") }),
    [string]$GenPrefix = $(if ($env:FASTDDSGEN_PREFIX) { $env:FASTDDSGEN_PREFIX } else { (Join-Path $BuildWorkRoot "fastddsgen-prefix") }),
    [string]$Workspace = $(if ($env:FASTDDS_WS) { $env:FASTDDS_WS } else { (Join-Path $BuildWorkRoot "fastdds-workspace") }),
    [string]$BuildRoot = $(if ($env:BUILD_ROOT) { $env:BUILD_ROOT } else { (Join-Path $BuildWorkRoot "generated-types") }),
    [string]$PackageVersion = $(if ($env:PKG_VERSION) { $env:PKG_VERSION } else { "" }),
    [string]$VcpkgRoot = $(if ($env:VCPKG_ROOT) { $env:VCPKG_ROOT } elseif ($env:VCPKG_INSTALLATION_ROOT) { $env:VCPKG_INSTALLATION_ROOT } else { (Join-Path $BuildWorkRoot "vcpkg") }),
    [string]$VcpkgTriplet = $(if ($env:VCPKG_DEFAULT_TRIPLET) { $env:VCPKG_DEFAULT_TRIPLET } else { "x64-windows" }),
    [string]$BuildArch = $(if ($env:LWRCLPY_WINDOWS_BUILD_ARCH) { $env:LWRCLPY_WINDOWS_BUILD_ARCH } else { "x64" }),
    [int]$Jobs = $(if ($env:JOBS) { [int]$env:JOBS } else { [Environment]::ProcessorCount })
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "build_env.ps1")
$BuildArch = Normalize-WindowsBuildArch $BuildArch
Initialize-WindowsBuildEnvironment $BuildArch

$Prefix = [System.IO.Path]::GetFullPath($Prefix)
$GenPrefix = [System.IO.Path]::GetFullPath($GenPrefix)
$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$BuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$VcpkgRoot = [System.IO.Path]::GetFullPath($VcpkgRoot)

& (Join-Path $PSScriptRoot "install_fastdds_v3_vcpkg.ps1") `
    -Prefix $Prefix `
    -GenPrefix $GenPrefix `
    -Workspace $Workspace `
    -VcpkgRoot $VcpkgRoot `
    -VcpkgTriplet $VcpkgTriplet `
    -BuildArch $BuildArch `
    -Jobs $Jobs
if ($LASTEXITCODE -ne 0) {
    throw "install_fastdds_v3_vcpkg.ps1 failed"
}

$fastddsgen = Join-Path $GenPrefix "bin\fastddsgen.bat"
if (-not (Test-Path $fastddsgen)) {
    $fastddsgen = Join-Path $GenPrefix "bin\fastddsgen"
}

& (Join-Path $PSScriptRoot "gen_python_types.ps1") `
    -Prefix $Prefix `
    -FastddsgenBin $fastddsgen `
    -BuildRoot $BuildRoot `
    -VcpkgRoot $VcpkgRoot `
    -VcpkgTriplet $VcpkgTriplet `
    -BuildArch $BuildArch `
    -Jobs $Jobs
if ($LASTEXITCODE -ne 0) {
    throw "gen_python_types.ps1 failed"
}

& (Join-Path $PSScriptRoot "make_pip_package_with_runtime.ps1") `
    -FastDdsPrefix $Prefix `
    -BuildRoot $BuildRoot `
    -VcpkgRoot $VcpkgRoot `
    -VcpkgTriplet $VcpkgTriplet `
    -BuildArch $BuildArch `
    -PackageVersion $PackageVersion
if ($LASTEXITCODE -ne 0) {
    throw "make_pip_package_with_runtime.ps1 failed"
}
