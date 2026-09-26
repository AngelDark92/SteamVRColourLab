[CmdletBinding()]
param(
    # Build machine only. The resulting package does not need installed Python.
    [string]$Python = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = Join-Path $repoRoot 'build\portable'
$distRoot = Join-Path $repoRoot 'dist'
$packagePath = Join-Path $distRoot 'SteamVRColourLab'
$zipPath = Join-Path $distRoot 'SteamVRColourLab-Windows-x64.zip'
$hashPath = "$zipPath.sha256"
# Official PyPI 6.22.3 supports CPython 3.8-3.15, including Python 3.14.
$pyInstallerVersion = '6.22.3'

function Assert-OwnedPath {
    param([string]$Path, [string]$Root, [switch]$InspectTree)
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $resolvedPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (-not $resolvedPath.StartsWith("$resolvedRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a path outside the owned directory: $resolvedPath"
    }
    # Check every existing ancestor, so an output directory cannot redirect writes.
    $cursor = $resolvedPath
    while ($cursor.Length -ge $resolvedRoot.Length) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -Force -LiteralPath $cursor
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing a junction or symbolic link: $cursor"
            }
        }
        if ($cursor -eq $resolvedRoot) { break }
        $cursor = Split-Path -Parent $cursor
    }
    if ($InspectTree -and (Test-Path -LiteralPath $resolvedPath -PathType Container)) {
        $linked = Get-ChildItem -Force -Recurse -LiteralPath $resolvedPath |
            Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } |
            Select-Object -First 1
        if ($linked) { throw "Refusing a tree containing a link: $($linked.FullName)" }
    }
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

$oldLocation = Get-Location
$oldPyInstallerCache = $env:PYINSTALLER_CONFIG_DIR
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Build the Windows package on Windows.' }
    Set-Location -LiteralPath $repoRoot
    $requiredFiles = @('app.py', 'requirements.txt', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'TEST_RESULTS.md')
    foreach ($name in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $name) -PathType Leaf)) {
            throw "Required source file is missing: $name"
        }
    }
    Assert-OwnedPath -Path (Join-Path $repoRoot 'examples') -Root $repoRoot -InspectTree
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'examples') -PathType Container)) {
        throw 'Required examples directory is missing.'
    }
    foreach ($path in @($buildRoot, $distRoot, $packagePath, $zipPath, $hashPath)) {
        Assert-OwnedPath -Path $path -Root $repoRoot
    }

    $pythonArgs = @()
    if ($Python) {
        $pythonCommand = (Get-Command -Name $Python -CommandType Application -ErrorAction Stop).Source
    } elseif (Test-Path -LiteralPath (Join-Path $repoRoot '.venv\Scripts\python.exe')) {
        $pythonCommand = Join-Path $repoRoot '.venv\Scripts\python.exe'
    } elseif (Get-Command -Name 'py.exe' -CommandType Application -ErrorAction SilentlyContinue) {
        $pythonCommand = (Get-Command -Name 'py.exe' -CommandType Application).Source
        $pythonArgs = @('-3')
    } else {
        throw 'Building requires full 64-bit CPython 3.11-3.15 with tkinter and pip. Install it or pass -Python C:\path\python.exe.'
    }
    $probeCode = @'
import json, platform, struct, sys, tkinter, venv, ensurepip
assert sys.implementation.name == 'cpython', 'Use CPython'
assert (3, 11) <= sys.version_info[:2] < (3, 16), 'Use Python 3.11-3.15'
assert struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64', 'x86_64'), 'Use Windows x64 Python'
print(json.dumps({'version': platform.python_version(), 'base': sys.base_prefix, 'executable': sys._base_executable}))
'@
    $probeOutput = & $pythonCommand @pythonArgs -c $probeCode
    if ($LASTEXITCODE -ne 0) { throw 'Python validation failed. A full Windows x64 Python installation with tkinter and pip is required.' }
    $pythonInfo = ($probeOutput -join "`n") | ConvertFrom-Json
    $buildEnvironment = Join-Path $buildRoot "venv-$($pythonInfo.version)-x64"
    $buildPython = Join-Path $buildEnvironment 'Scripts\python.exe'
    Assert-OwnedPath -Path $buildEnvironment -Root $buildRoot -InspectTree
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
        Invoke-Checked -Executable $pythonInfo.executable -Arguments @('-m', 'venv', $buildEnvironment)
    }
    Invoke-Checked -Executable $buildPython -Arguments @('-c', $probeCode)
    Invoke-Checked -Executable $buildPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $repoRoot 'requirements.txt'), "pyinstaller==$pyInstallerVersion")
    Invoke-Checked -Executable $buildPython -Arguments @('-m', 'pip', 'check')
    $appVersion = & $buildPython -c 'from colourlab import __version__; print(__version__)'
    if ($LASTEXITCODE -ne 0) { throw 'Could not read application version.' }
    $sourceCommit = $null
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $commitOutput = & git -C $repoRoot rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0) { $sourceCommit = "$commitOutput".Trim() }
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $staging = Join-Path $buildRoot "staging-$stamp"
    Assert-OwnedPath -Path $staging -Root $buildRoot
    New-Item -ItemType Directory -Path $staging | Out-Null
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $staging 'cache'
    $arguments = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--console',
        '--name', 'SteamVRColourLab', '--distpath', (Join-Path $staging 'dist'),
        '--workpath', (Join-Path $staging 'work'), '--specpath', $staging,
        '--collect-all', 'openvr', '--collect-all', 'glfw',
        '--copy-metadata', 'openvr', '--copy-metadata', 'glfw', '--copy-metadata', 'Pillow',
        (Join-Path $repoRoot 'app.py')
    )
    Invoke-Checked -Executable $buildPython -Arguments $arguments
    $stagedPackage = Join-Path $staging 'dist\SteamVRColourLab'
    if (-not (Test-Path -LiteralPath (Join-Path $stagedPackage 'SteamVRColourLab.exe') -PathType Leaf)) {
        throw 'PyInstaller did not create the expected executable.'
    }
    foreach ($name in @('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'TEST_RESULTS.md')) {
        Copy-Item -LiteralPath (Join-Path $repoRoot $name) -Destination $stagedPackage
    }
    Copy-Item -LiteralPath (Join-Path $repoRoot 'examples') -Destination $stagedPackage -Recurse
    foreach ($name in @('PORTABLE-VR-VALIDATION.md', 'SCENE-MENU-FIX-20260925.md', 'dashboard-source.png')) {
        $source = Join-Path $repoRoot "validation\$name"
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Assert-OwnedPath -Path $source -Root $repoRoot
            $validationDirectory = Join-Path $stagedPackage 'validation'
            New-Item -ItemType Directory -Path $validationDirectory -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $validationDirectory
        }
    }
    $licenses = Join-Path $stagedPackage 'licenses'
    New-Item -ItemType Directory -Path $licenses | Out-Null
    Copy-Item -LiteralPath (Join-Path $pythonInfo.base 'LICENSE.txt') -Destination (Join-Path $licenses 'CPython-LICENSE.txt')
    foreach ($component in @('tcl', 'tk')) {
        $componentDirectories = Get-ChildItem -LiteralPath (Join-Path $pythonInfo.base 'tcl') -Directory -Filter "$component*"
        foreach ($directory in $componentDirectories) {
            $license = Join-Path $directory.FullName 'license.terms'
            if (Test-Path -LiteralPath $license -PathType Leaf) {
                Copy-Item -LiteralPath $license -Destination (Join-Path $licenses "$($directory.Name)-license.terms")
            }
        }
    }
    # Preserve exact installed-wheel notices, including complete nested license
    # trees. The OpenVR/GLFW wheels omit their native SDK notices, so fetch only
    # those 2 texts from matching official release tags and verify fixed hashes.
    $licenseCode = @'
import hashlib, json, shutil, sys, urllib.request
from importlib.metadata import distribution
from pathlib import Path
import glfw, openvr

destination = Path(sys.argv[1])
cache = Path(sys.argv[2])
records = []
for name in ('openvr', 'glfw', 'Pillow', 'PyInstaller'):
    package = distribution(name)
    notices = []
    for entry in package.files or ():
        parts = entry.parts
        metadata_index = next((i for i, part in enumerate(parts) if part.endswith('.dist-info')), None)
        if metadata_index is None:
            continue
        relative = parts[metadata_index + 1:]
        if not any(part.lower().startswith(('license', 'copying', 'notice')) for part in relative):
            continue
        if '..' in relative:
            raise RuntimeError(f'Unsafe license path in {name}: {entry}')
        source = Path(package.locate_file(entry))
        if not source.is_file():
            raise RuntimeError(f'Missing installed license: {source}')
        target = destination.joinpath(name, *relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        notices.append({'file': str(target.relative_to(destination)), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    if not notices:
        raise RuntimeError(f'No installed license notices found for {name}')
    records.append({'distribution': name, 'version': package.version, 'notices': notices})

if (openvr.k_nSteamVRVersionMajor, openvr.k_nSteamVRVersionMinor, openvr.k_nSteamVRVersionBuild) != (2, 12, 14):
    raise RuntimeError('OpenVR SDK changed; update the pinned native license source')
if tuple(glfw.get_version()) != (3, 4, 0):
    raise RuntimeError('GLFW native version changed; update the pinned native license source')
cache.mkdir(parents=True, exist_ok=True)
native_notices = (
    ('OpenVR-v2.12.14-LICENSE.txt', 'https://raw.githubusercontent.com/ValveSoftware/openvr/v2.12.14/LICENSE', 'f56ff606104d4ef18e617921a75c73ad73b5a1a1d70c69590c29de16919e04ad'),
    ('GLFW-3.4-LICENSE.txt', 'https://raw.githubusercontent.com/glfw/glfw/3.4/LICENSE.md', '149704059b5d0bf551637e50042dd4de9c2cae921021f6636298911e3a5f9462'),
)
for filename, url, expected_hash in native_notices:
    cached = cache / filename
    if not cached.is_file() or hashlib.sha256(cached.read_bytes()).hexdigest() != expected_hash:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise RuntimeError(f'License checksum mismatch: {url}')
        cached.write_bytes(content)
    shutil.copyfile(cached, destination / filename)
    records.append({'file': filename, 'source': url, 'sha256': expected_hash})
(destination / 'MANIFEST.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
'@
    $licenseCache = Join-Path $buildRoot 'license-cache'
    Assert-OwnedPath -Path $licenseCache -Root $buildRoot -InspectTree
    Invoke-Checked -Executable $buildPython -Arguments @('-c', $licenseCode, $licenses, $licenseCache)
    # These launchers never install anything or invoke external Python.
    $launchers = @{ 'start_windows.bat' = ''; 'preview_windows.bat' = '--desktop '; 'self_test_windows.bat' = '--self-test ' }
    foreach ($name in $launchers.Keys) {
        $launcher = "@echo off`r`nsetlocal`r`ncd /d `"%~dp0`"`r`n`"%~dp0SteamVRColourLab.exe`" $($launchers[$name])%*`r`nset `"app_exit=%errorlevel%`"`r`nif not `"%app_exit%`"==`"0`" (`r`n  echo Colour Lab stopped with exit code %app_exit%. See the runs folder for logs.`r`n  pause`r`n)`r`nexit /b %app_exit%`r`n"
        Set-Content -LiteralPath (Join-Path $stagedPackage $name) -Value $launcher -Encoding Ascii -NoNewline
    }
    $buildRecord = [ordered]@{
        version = "$appVersion".Trim()
        source_commit = $sourceCommit
        built_at = (Get-Date).ToUniversalTime().ToString('o')
        python = $pythonInfo.version
        pyinstaller = $pyInstallerVersion
        requirements_sha256 = (Get-FileHash -LiteralPath (Join-Path $repoRoot 'requirements.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
        validation = 'Package build only. Run self_test_windows.bat for local GPU validation; headset interaction requires SteamVR runtime validation.'
    }
    $buildRecord | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stagedPackage 'BUILD_INFO.json') -Encoding UTF8

    New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
    # Retain the old folder, including any settings and session reports it holds.
    if (Test-Path -LiteralPath $packagePath) {
        Assert-OwnedPath -Path $packagePath -Root $distRoot -InspectTree
        $previousPackage = Join-Path $buildRoot "previous-$stamp"
        Assert-OwnedPath -Path $previousPackage -Root $buildRoot
        Move-Item -LiteralPath $packagePath -Destination $previousPackage
        Write-Host "Previous package and any saved data retained: $previousPackage"
    }
    Assert-OwnedPath -Path $stagedPackage -Root $staging -InspectTree
    Assert-OwnedPath -Path $packagePath -Root $distRoot
    Move-Item -LiteralPath $stagedPackage -Destination $packagePath
    foreach ($path in @($zipPath, $hashPath)) { Assert-OwnedPath -Path $path -Root $distRoot }
    Compress-Archive -LiteralPath $packagePath -DestinationPath $zipPath -CompressionLevel Optimal -Force
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $hashPath -Value "$hash  $([IO.Path]::GetFileName($zipPath))" -Encoding Ascii
    # Restore portable user data only after creating the clean distributable ZIP.
    # The prior package remains an intact backup; never copy user data into ZIP.
    if (Get-Variable -Name previousPackage -ErrorAction SilentlyContinue) {
        foreach ($dataName in @('runs', 'settings')) {
            $sourceData = Join-Path $previousPackage $dataName
            if (Test-Path -LiteralPath $sourceData -PathType Container) {
                Assert-OwnedPath -Path $sourceData -Root $buildRoot -InspectTree
                $destinationData = Join-Path $packagePath $dataName
                Assert-OwnedPath -Path $destinationData -Root $packagePath
                Copy-Item -LiteralPath $sourceData -Destination $destinationData -Recurse
                Write-Host "Preserved portable user data: $destinationData"
            }
        }
    }
    Write-Host "Built portable package: $packagePath"
    Write-Host "Archive: $zipPath"
    Write-Host "SHA256: $hash"
    Write-Host "Build staging retained for inspection: $staging"
} catch {
    Write-Error -Message $_ -ErrorAction Continue
    exit 1
} finally {
    $env:PYINSTALLER_CONFIG_DIR = $oldPyInstallerCache
    Set-Location -LiteralPath $oldLocation.Path
}
