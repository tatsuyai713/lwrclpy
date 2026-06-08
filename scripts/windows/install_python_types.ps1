param(
    [string]$BuildRoot = $(if ($env:BUILD_ROOT) { $env:BUILD_ROOT } else { (Join-Path (Get-Location) "._types_python_build_v3") }),
    [string]$InstallRoot = $(if ($env:INSTALL_ROOT) { $env:INSTALL_ROOT } else { python -c "import sysconfig; print(sysconfig.get_paths()['platlib'])" })
)

$ErrorActionPreference = "Stop"

function Ensure-Init($Dir) {
    if (-not (Test-Path $Dir)) {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    }
    $init = Join-Path $Dir "__init__.py"
    if (-not (Test-Path $init)) {
        "# auto-generated" | Set-Content -Path $init -Encoding UTF8
    }
}

$srcRoot = Join-Path $BuildRoot "src"
if (-not (Test-Path $srcRoot)) {
    throw "BUILD_ROOT/src not found: $srcRoot"
}

Write-Host "[INFO] BUILD_ROOT=$BuildRoot"
Write-Host "[INFO] INSTALL_ROOT=$InstallRoot"
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null

$typeDirs = Get-ChildItem -Path $srcRoot -Directory -Recurse |
    Where-Object {
        $parts = $_.FullName.Substring($srcRoot.Length).TrimStart([char[]]@("\", "/")) -split "[\\/]"
        $parts.Length -eq 3 -and $parts[1] -in @("msg", "srv", "action")
    }

foreach ($typeDir in $typeDirs) {
    $parts = $typeDir.FullName.Substring($srcRoot.Length).TrimStart([char[]]@("\", "/")) -split "[\\/]"
    $pkg = $parts[0]
    $ns = $parts[1]
    $name = $parts[2]
    $build = Join-Path $typeDir.FullName "build"
    $pySrc = Join-Path $build "$name.py"
    if (-not (Test-Path $pySrc)) {
        Write-Host "[SKIP] $pkg/$ns/$name: missing $name.py"
        continue
    }

    $wrapper = Get-ChildItem -Path $build -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "_${name}Wrapper.*" -and ($_.Extension -in @(".pyd", ".dll")) } |
        Sort-Object Name |
        Select-Object -First 1
    if (-not $wrapper) {
        Write-Host "[SKIP] $pkg/$ns/$name: missing wrapper .pyd/.dll"
        continue
    }

    $core = Get-ChildItem -Path $build -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @("$name.dll", "lib$name.dll") } |
        Sort-Object Name |
        Select-Object -First 1

    $dstPkg = Join-Path $InstallRoot (Join-Path $pkg $ns)
    Ensure-Init (Join-Path $InstallRoot $pkg)
    Ensure-Init $dstPkg

    Write-Host "[INST] $pkg/$ns/$name"
    Copy-Item $pySrc (Join-Path $dstPkg "$name.py") -Force

    $wrapperName = $wrapper.Name
    if ($wrapper.Extension -eq ".dll") {
        $wrapperName = "_${name}Wrapper.pyd"
    }
    Copy-Item $wrapper.FullName (Join-Path $dstPkg $wrapperName) -Force
    if ($core) {
        Copy-Item $core.FullName (Join-Path $dstPkg $core.Name) -Force
    }

    $init = Join-Path $dstPkg "__init__.py"
    $export = "from .$name import $name as $name"
    $content = Get-Content $init -Raw
    if (-not $content.Contains($export)) {
        Add-Content -Path $init -Value $export
    }
}

Write-Host "[OK] Installation finished."
