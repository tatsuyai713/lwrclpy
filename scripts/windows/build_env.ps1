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

function Import-VisualStudioEnvironment {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        return
    }

    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) {
        return
    }

    $devCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
    if (Test-Path $devCmd) {
        Write-Host "[INFO] Loading Visual Studio build environment: $installPath"
        $envLines = cmd /s /c "`"$devCmd`" -arch=amd64 -host_arch=amd64 >nul && set"
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
    & $javaExe -version
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
            & $javaCommand.Source -version
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
    Import-VisualStudioEnvironment
    Add-PythonScriptsPath
    Add-JavaPath
}
