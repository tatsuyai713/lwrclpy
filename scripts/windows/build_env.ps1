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

function Add-JavaPath {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $localJdk = Get-ChildItem -Path (Join-Path $repoRoot ".tools") -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "jdk-21*" -or $_.Name -like "jdk-17*" } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if ($localJdk) {
        $env:JAVA_HOME = $localJdk.FullName
        Add-PathEntry (Join-Path $env:JAVA_HOME "bin")
        return
    }

    if (Get-Command java -ErrorAction SilentlyContinue) {
        return
    }
    if ($env:JAVA_HOME) {
        Add-PathEntry (Join-Path $env:JAVA_HOME "bin")
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
        if ($java) {
            Add-PathEntry $java.Directory.FullName
            return
        }
    }
}

function Initialize-WindowsBuildEnvironment {
    Import-VisualStudioEnvironment
    Add-PythonScriptsPath
    Add-JavaPath
}
