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

Write-Host "[WARN] install_fastdds_v3_colcon.ps1 is kept for compatibility. Windows now installs Fast DDS through vcpkg."

& (Join-Path $PSScriptRoot "install_fastdds_v3_vcpkg.ps1") `
    -BuildWorkRoot $BuildWorkRoot `
    -Prefix $Prefix `
    -GenPrefix $GenPrefix `
    -Workspace $Workspace `
    -ReposRef $ReposRef `
    -FastDdsGenRef $FastDdsGenRef `
    -VcpkgRoot $VcpkgRoot `
    -VcpkgTriplet $VcpkgTriplet `
    -BuildArch $BuildArch `
    -Jobs $Jobs
