$ErrorActionPreference = "Stop"

function Add-PathEntry {
    param([string]$Path)
    if ($Path -and (Test-Path $Path)) {
        $entries = $env:PATH -split ';'
        if ($entries -notcontains $Path) {
            $env:PATH = "$Path;$env:PATH"
        }
    }
}

function Normalize-WindowsBuildArch {
    param([string]$BuildArch)
    if (-not $BuildArch) {
        $BuildArch = $(if ($env:LWRCLPY_WINDOWS_BUILD_ARCH) { $env:LWRCLPY_WINDOWS_BUILD_ARCH } else { "x64" })
    }

    switch ($BuildArch.ToLowerInvariant()) {
        "x64" { return "x64" }
        "amd64" { return "x64" }
        "arm64" { return "arm64" }
        "aarch64" { return "arm64" }
        default { throw "Unsupported Windows build architecture: $BuildArch" }
    }
}

function Get-VsDevCmdArch {
    param([string]$BuildArch)
    if ((Normalize-WindowsBuildArch $BuildArch) -eq "arm64") {
        return "arm64"
    }
    return "amd64"
}

function Get-VsRequiredComponent {
    param([string]$BuildArch)
    if ((Normalize-WindowsBuildArch $BuildArch) -eq "arm64") {
        return "Microsoft.VisualStudio.Component.VC.Tools.ARM64"
    }
    return "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
}

function Import-VisualStudioEnvironment {
    param([string]$BuildArch = $(if ($env:LWRCLPY_WINDOWS_BUILD_ARCH) { $env:LWRCLPY_WINDOWS_BUILD_ARCH } else { "x64" }))

    $BuildArch = Normalize-WindowsBuildArch $BuildArch
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        return
    }

    $requiredComponent = Get-VsRequiredComponent $BuildArch
    $installPath = & $vswhere -latest -products * -requires $requiredComponent -property installationPath
    if (-not $installPath -and $BuildArch -eq "arm64") {
        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    }
    if (-not $installPath) {
        return
    }

    $devCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
    if (Test-Path $devCmd) {
        $vsArch = Get-VsDevCmdArch $BuildArch
        Write-Host "[INFO] Loading Visual Studio build environment: $installPath ($BuildArch)"
        $envLines = cmd /s /c "`"$devCmd`" -arch=$vsArch -host_arch=$vsArch >nul && set"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to load Visual Studio build environment for $BuildArch"
        }
        foreach ($line in $envLines) {
            $idx = $line.IndexOf("=")
            if ($idx -gt 0) {
                [Environment]::SetEnvironmentVariable($line.Substring(0, $idx), $line.Substring($idx + 1), "Process")
            }
        }
    }

    Add-PathEntry (Join-Path $installPath "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin")
    Add-PathEntry (Join-Path $installPath "Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja")
}

function Add-PythonScriptsPath {
    $scripts = python -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Add-PathEntry $scripts
    }
}

function Get-JavaMajorVersion {
    param([string]$JavaExe)
    if (-not $JavaExe -or -not (Test-Path $JavaExe)) {
        return 0
    }
    $versionOutput = & $JavaExe -version 2>&1
    $line = ($versionOutput | Select-Object -First 1)
    if (-not $line) {
        return 0
    }
    if ($line -match 'version "1\.(\d+)\.') {
        return [int]$Matches[1]
    }
    if ($line -match 'version "(\d+)') {
        return [int]$Matches[1]
    }
    return 0
}

function Use-JavaHome {
    param([string]$JavaHome)
    if (-not $JavaHome) {
        return $false
    }
    $javaExe = Join-Path $JavaHome "bin\java.exe"
    if (-not (Test-Path $javaExe)) {
        return $false
    }
    $major = Get-JavaMajorVersion $javaExe
    if ($major -lt 17) {
        return $false
    }
    $env:JAVA_HOME = $JavaHome
    Add-PathEntry (Join-Path $env:JAVA_HOME "bin")
    Write-Host "[INFO] Using JAVA_HOME=$env:JAVA_HOME"
    & $javaExe -version 2>&1 | Out-Host
    return $true
}

function Add-JavaPath {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    if (Use-JavaHome $env:JAVA_HOME) {
        return
    }
    if ($env:JAVA_HOME) {
        Write-Host "[WARN] Ignoring JAVA_HOME=$env:JAVA_HOME because it is not Java 17 or newer"
    }

    $localJdk = Get-ChildItem -Path (Join-Path $repoRoot ".tools") -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "jdk-21*" -or $_.Name -like "jdk-17*" } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if ($localJdk -and (Use-JavaHome $localJdk.FullName)) {
        return
    }

    $javaCommand = Get-Command java -ErrorAction SilentlyContinue
    if ($javaCommand) {
        $major = Get-JavaMajorVersion $javaCommand.Source
        if ($major -ge 17) {
            Add-PathEntry (Split-Path $javaCommand.Source -Parent)
            Write-Host "[INFO] Using java from PATH: $($javaCommand.Source)"
            & $javaCommand.Source -version 2>&1 | Out-Host
            return
        }
        Write-Host "[WARN] Ignoring java from PATH because it is version $major"
    }

    if ($env:JAVA_HOME -and (Use-JavaHome $env:JAVA_HOME)) {
        return
    }

    $roots = @(
        (Join-Path $env:ProgramFiles "Java"),
        (Join-Path $env:ProgramFiles "Eclipse Adoptium"),
        (Join-Path $env:ProgramFiles "Microsoft")
    ) | Where-Object { Test-Path $_ }
    foreach ($root in $roots) {
        $java = Get-ChildItem -Path $root -Recurse -Filter java.exe -File -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($java -and (Use-JavaHome (Split-Path $java.Directory.FullName -Parent))) {
            return
        }
    }

    throw "Java 17 or newer is required for Fast-DDS-Gen Gradle, but no suitable JVM was found"
}

function Initialize-WindowsBuildEnvironment {
    param([string]$BuildArch = $(if ($env:LWRCLPY_WINDOWS_BUILD_ARCH) { $env:LWRCLPY_WINDOWS_BUILD_ARCH } else { "x64" }))

    $BuildArch = Normalize-WindowsBuildArch $BuildArch
    if ($env:LWRCLPY_WINDOWS_BUILD_ENV_INITIALIZED -eq $BuildArch) {
        return
    }

    $env:LWRCLPY_WINDOWS_BUILD_ARCH = $BuildArch
    Import-VisualStudioEnvironment $BuildArch
    Add-PythonScriptsPath
    Add-JavaPath
    $env:LWRCLPY_WINDOWS_BUILD_ENV_INITIALIZED = $BuildArch
}
