param(
    [switch]$Integration
)

$ErrorActionPreference = "Stop"

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("lwrclpy-openssl-test-" + [guid]::NewGuid())
. (Join-Path $PSScriptRoot "make_pip_package_with_runtime.ps1") `
    -BuildWorkRoot $testRoot `
    -BuildRoot (Join-Path $testRoot "generated-types") `
    -FastDdsPrefix (Join-Path $testRoot "fastdds-prefix") `
    -VcpkgRoot (Join-Path $testRoot "vcpkg") `
    -BuildArch x64 `
    -FunctionsOnly

function New-TestPe($Path, [uint16]$Machine) {
    $bytes = New-Object byte[] 128
    [System.BitConverter]::GetBytes([uint16]0x5A4D).CopyTo($bytes, 0)
    [System.BitConverter]::GetBytes([uint32]0x40).CopyTo($bytes, 0x3C)
    [System.BitConverter]::GetBytes([uint32]0x00004550).CopyTo($bytes, 0x40)
    [System.BitConverter]::GetBytes($Machine).CopyTo($bytes, 0x44)
    [System.IO.File]::WriteAllBytes($Path, $bytes)
}

function Assert-Equal($Expected, $Actual, $Message) {
    if ($Expected -ne $Actual) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

try {
    $sourceRoot = Join-Path $testRoot "python"
    $wrongArchRoot = Join-Path $testRoot "wrong-arch"
    $expectedRoot = Join-Path $testRoot "vcpkg"
    $destination = Join-Path $testRoot "vendor"
    New-Item -ItemType Directory -Path $sourceRoot, $wrongArchRoot, $expectedRoot, $destination -Force | Out-Null
    $x64Generic = Join-Path $sourceRoot "libssl-3.dll"
    $x64CryptoGeneric = Join-Path $sourceRoot "libcrypto-3.dll"
    $arm64NamedX64 = Join-Path $wrongArchRoot "libssl-3-x64.dll"
    $arm64Generic = Join-Path $wrongArchRoot "libcrypto-3.dll"
    $expectedSsl = Join-Path $expectedRoot "libssl-3-x64.dll"
    $expectedCrypto = Join-Path $expectedRoot "libcrypto-3-x64.dll"
    New-TestPe $x64Generic 0x8664
    New-TestPe $x64CryptoGeneric 0x8664
    New-TestPe $arm64NamedX64 0xAA64
    New-TestPe $arm64Generic 0xAA64
    New-TestPe $expectedSsl 0x8664
    New-TestPe $expectedCrypto 0x8664

    Assert-Equal "x64" (Get-PeArchitecture $x64Generic) "x64 PE detection failed."
    Assert-Equal "arm64" (Get-PeArchitecture $arm64Generic) "ARM64 PE detection failed."

    $script:OpenSslTestCandidates = @(
        Get-Item $arm64NamedX64
        Get-Item $x64Generic
    )
    function Get-SignedPythonOpenSslDlls($Kind) {
        return $script:OpenSslTestCandidates
    }

    $selected = Select-SignedPythonOpenSslDll "ssl" "libssl-3-x64.dll"
    Assert-Equal $x64Generic $selected.FullName "A generic-name DLL with the correct PE architecture was not selected."

    $script:OpenSslTestCandidates = @(Get-Item $arm64NamedX64)
    try {
        Select-SignedPythonOpenSslDll "ssl" "libssl-3-x64.dll" | Out-Null
        throw "An ARM64 DLL with an x64-looking filename was incorrectly accepted."
    } catch {
        if ($_.Exception.Message -notmatch "No signed Python libssl DLL matches") {
            throw
        }
    }

    $script:OpenSslTestCandidatesByKind = @{
        ssl = @(Get-Item $x64Generic)
        crypto = @(Get-Item $x64CryptoGeneric)
    }
    function Get-SignedPythonOpenSslDlls($Kind) {
        return $script:OpenSslTestCandidatesByKind[$Kind]
    }
    function Test-ValidAuthenticodeSignature($Path) {
        return $true
    }

    Copy-SignedPythonOpenSslDlls $destination @($expectedRoot)
    foreach ($expectedFile in @(
        "libssl-3-x64.dll",
        "libssl-3.dll",
        "libcrypto-3-x64.dll",
        "libcrypto-3.dll"
    )) {
        if (-not (Test-Path (Join-Path $destination $expectedFile))) {
            throw "Expected vendored DLL was not created: $expectedFile"
        }
    }

    Write-Host "OpenSSL runtime selection tests passed."
} finally {
    if (Test-Path $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}

if ($Integration) {
    . (Join-Path $PSScriptRoot "make_pip_package_with_runtime.ps1") `
        -BuildWorkRoot $testRoot `
        -BuildRoot (Join-Path $testRoot "generated-types") `
        -FastDdsPrefix (Join-Path $testRoot "fastdds-prefix") `
        -VcpkgRoot (Join-Path $testRoot "vcpkg") `
        -BuildArch x64 `
        -FunctionsOnly

    try {
        $actualExpectedRoot = Join-Path $testRoot "expected"
        $actualDestination = Join-Path $testRoot "vendor"
        New-Item -ItemType Directory -Path $actualExpectedRoot, $actualDestination -Force | Out-Null
        [System.IO.File]::WriteAllBytes((Join-Path $actualExpectedRoot "libssl-3-x64.dll"), [byte[]]@())
        [System.IO.File]::WriteAllBytes((Join-Path $actualExpectedRoot "libcrypto-3-x64.dll"), [byte[]]@())

        foreach ($kind in @("ssl", "crypto")) {
            $selected = Select-SignedPythonOpenSslDll $kind "lib$kind-3-x64.dll"
            Assert-Equal "x64" (Get-PeArchitecture $selected.FullName) "Actual signed Python lib$kind architecture mismatch."
            if (-not (Test-ValidAuthenticodeSignature $selected.FullName)) {
                throw "Actual Python lib$kind DLL is not Authenticode-valid: $($selected.FullName)"
            }
        }

        Copy-SignedPythonOpenSslDlls $actualDestination @($actualExpectedRoot)
        foreach ($expectedFile in @(
            "libssl-3-x64.dll",
            "libssl-3.dll",
            "libcrypto-3-x64.dll",
            "libcrypto-3.dll"
        )) {
            $actualFile = Join-Path $actualDestination $expectedFile
            if (-not (Test-Path $actualFile)) {
                throw "Expected actual vendored DLL was not created: $expectedFile"
            }
            Assert-Equal "x64" (Get-PeArchitecture $actualFile) "Actual vendored DLL architecture mismatch."
            if (-not (Test-ValidAuthenticodeSignature $actualFile)) {
                throw "Actual vendored DLL is not Authenticode-valid: $actualFile"
            }
        }

        Write-Host "Actual signed Python OpenSSL integration tests passed."
    } finally {
        if (Test-Path $testRoot) {
            Remove-Item -LiteralPath $testRoot -Recurse -Force
        }
    }
}
