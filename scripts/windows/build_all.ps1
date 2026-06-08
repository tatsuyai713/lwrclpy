param(
    [string]$Prefix = $(if ($env:FASTDDS_PREFIX) { $env:FASTDDS_PREFIX } else { "C:\fast-dds-v3" }),
    [string]$GenPrefix = $(if ($env:FASTDDSGEN_PREFIX) { $env:FASTDDSGEN_PREFIX } else { "C:\fast-dds-gen-v3" }),
    [string]$BuildRoot = $(if ($env:BUILD_ROOT) { $env:BUILD_ROOT } else { (Join-Path (Get-Location) "._types_python_build_v3") }),
    [string]$PackageVersion = $(if ($env:PKG_VERSION) { $env:PKG_VERSION } else { "" }),
    [string]$VcpkgRoot = $(if ($env:VCPKG_ROOT) { $env:VCPKG_ROOT } elseif ($env:VCPKG_INSTALLATION_ROOT) { $env:VCPKG_INSTALLATION_ROOT } else { "C:\vcpkg" }),
    [string]$VcpkgTriplet = $(if ($env:VCPKG_DEFAULT_TRIPLET) { $env:VCPKG_DEFAULT_TRIPLET } else { "x64-windows" }),
    [int]$Jobs = $(if ($env:JOBS) { [int]$env:JOBS } else { [Environment]::ProcessorCount })
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "install_fastdds_v3_vcpkg.ps1") `
    -Prefix $Prefix `
    -GenPrefix $GenPrefix `
    -VcpkgRoot $VcpkgRoot `
    -VcpkgTriplet $VcpkgTriplet `
    -Jobs $Jobs

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
    -Jobs $Jobs

& (Join-Path $PSScriptRoot "make_pip_package_with_runtime.ps1") `
    -FastDdsPrefix $Prefix `
    -BuildRoot $BuildRoot `
    -VcpkgRoot $VcpkgRoot `
    -VcpkgTriplet $VcpkgTriplet `
    -PackageVersion $PackageVersion
