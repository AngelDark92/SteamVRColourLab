# Shared path checks and conservative cleanup for the portable Windows builder.
function Assert-OwnedPath {
    param([string]$Path, [string]$Root, [switch]$InspectTree, [switch]$RejectMetadata)
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $resolvedPath = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    if (-not $resolvedPath.StartsWith("$resolvedRoot$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing a path outside the owned directory: $resolvedPath"
    }
    # Include ancestors above Root: an owned directory may itself be redirected.
    $cursor = $resolvedPath
    while ($cursor) {
        $item = Get-Item -Force -LiteralPath $cursor -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing a junction or symbolic link: $cursor"
        }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    if ($InspectTree -and (Test-Path -LiteralPath $resolvedPath -PathType Container)) {
        # Explicit traversal never follows a reparse point, even on PowerShell 5.1.
        $pending = New-Object 'System.Collections.Generic.Stack[string]'
        $pending.Push($resolvedPath)
        while ($pending.Count) {
            foreach ($child in Get-ChildItem -Force -LiteralPath $pending.Pop() -ErrorAction Stop) {
                if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Refusing a tree containing a link: $($child.FullName)"
                }
                if ($RejectMetadata -and $child.Name -in @('.git', '.github', '.codex', '.agents')) {
                    throw "Refusing a tree containing protected metadata: $($child.FullName)"
                }
                if ($child.PSIsContainer) { $pending.Push($child.FullName) }
            }
        }
    }
}

function Get-PortableFileHash {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Get-PortableArchiveManifest {
    param([string]$ZipPath, [string]$HashPath)
    $manifest = @{}
    $archive = $null
    try {
        if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf) -or
            -not (Test-Path -LiteralPath $HashPath -PathType Leaf)) {
            throw 'Previous archive or checksum is missing.'
        }
        foreach ($path in @($ZipPath, $HashPath)) {
            Assert-OwnedPath -Path $path -Root (Split-Path -Parent $path)
        }
        $checksum = (Get-Content -Raw -LiteralPath $HashPath).Trim()
        if ($checksum -notmatch '^([a-fA-F0-9]{64})\s+\*?([^\r\n]+)$' -or
            $Matches[2] -cne [IO.Path]::GetFileName($ZipPath)) {
            throw 'Previous archive checksum record is invalid.'
        }
        $expectedHash = $Matches[1]
        if ((Get-PortableFileHash -Path $ZipPath) -ne $expectedHash) {
            throw 'Previous archive checksum does not match.'
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
        $seen = @{}
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            $parts = $name.TrimEnd('/').Split('/')
            if ($parts.Count -lt 2 -or $parts[0] -cne 'SteamVRColourLab' -or
                @($parts | Where-Object { $_ -eq '' -or $_ -in @('.', '..', '.git', '.github', '.codex', '.agents') -or
                    $_ -match '[<>:"|?*\x00-\x1f]' -or $_ -match '[. ]$' -or
                    $_ -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)' }).Count) {
                throw "Previous archive contains an unsafe entry: $name"
            }
            $relative = ($parts[1..($parts.Count - 1)] -join '/')
            if ($seen.ContainsKey($relative)) { throw "Previous archive contains duplicate entries: $name" }
            $seen[$relative] = $true
            # Unix symlinks also cannot confer deletion authority.
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) {
                throw "Previous archive contains a symbolic link: $name"
            }
            if ($name.EndsWith('/')) { continue }
            $stream = $entry.Open()
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                $manifest[$relative] = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
            } finally {
                $sha.Dispose()
                $stream.Dispose()
            }
        }
    } catch {
        $manifest = @{}
        Write-Warning "Old package cleanup has no verified archive manifest; preserving unproven files. $($_.Exception.Message)"
    } finally {
        if ($archive) { $archive.Dispose() }
    }
    return $manifest
}

function Clear-StalePortableBuildFiles {
    param(
        [Parameter(Mandatory = $true)][string]$BuildRoot,
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [string]$CurrentEnvironment = '',
        [int]$KeepDays = 7,
        [int]$KeepPrevious = 1,
        [switch]$Apply
    )
    $result = [pscustomobject]@{
        Applied = [bool]$Apply
        Candidates = @()
        Removed = @()
        Refused = @()
        RemovedBytes = [long]0
        RemovedFiles = 0
        Error = $null
    }
    try {
        $root = [IO.Path]::GetFullPath($BuildRoot).TrimEnd('\', '/')
        $package = [IO.Path]::GetFullPath($PackagePath).TrimEnd('\', '/')
        if ((Split-Path -Leaf $root) -ne 'portable' -or (Split-Path -Leaf (Split-Path -Parent $root)) -ne 'build') {
            throw "Refusing an unexpected portable build root: $root"
        }
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Portable build root is missing: $root" }
        if (-not (Test-Path -LiteralPath $package -PathType Container)) { throw "Current package is missing: $package" }
        Assert-OwnedPath -Path $package -Root (Split-Path -Parent $package) -InspectTree -RejectMetadata

        $candidates = New-Object 'System.Collections.Generic.List[object]'
        $refused = New-Object 'System.Collections.Generic.List[object]'
        $previous = @(Get-ChildItem -Force -LiteralPath $root -Directory |
            Where-Object { $_.Name -match '^previous-\d{8}-\d{6}-\d{3}$' } |
            Sort-Object Name -Descending)
        $keptPrevious = @{}
        for ($index = 0; $index -lt [Math]::Min($KeepPrevious, $previous.Count); $index++) {
            $keptPrevious[$previous[$index].Name] = $true
        }

        foreach ($directory in @(Get-ChildItem -Force -LiteralPath $root -Directory)) {
            $name = $directory.Name
            $kind = $null
            if ($name -match '^staging-\d{8}-\d{6}-\d{3}$') { $kind = 'staging' }
            elseif ($name -match '^previous-\d{8}-\d{6}-\d{3}$') { $kind = 'previous' }
            elseif ($name -match '^relocated-[A-Za-z0-9._-]+$') { $kind = 'relocated' }
            elseif ($name -match '^venv-.+-x64$') { $kind = 'venv' }
            if (-not $kind) { continue }
            if ($kind -eq 'venv' -and $CurrentEnvironment -and $name -eq $CurrentEnvironment) { continue }
            if ($kind -eq 'previous' -and $keptPrevious.ContainsKey($name)) { continue }

            try {
                Assert-OwnedPath -Path $directory.FullName -Root $root -InspectTree -RejectMetadata
            } catch {
                $refused.Add([pscustomobject]@{ Path = $directory.FullName; Reason = $_.Exception.Message })
                continue
            }

            $files = @(Get-ChildItem -Force -Recurse -File -LiteralPath $directory.FullName -ErrorAction Stop)
            $bytes = [long]0
            $newest = $directory.LastWriteTimeUtc
            foreach ($file in $files) {
                $bytes += $file.Length
                if ($file.LastWriteTimeUtc -gt $newest) { $newest = $file.LastWriteTimeUtc }
            }
            if ($files.Count -eq 0) { continue }
            if ($KeepDays -gt 0 -and $newest -gt [DateTime]::UtcNow.AddDays(-$KeepDays)) { continue }

            $reason = $null
            $dataDirectories = @(Get-ChildItem -Force -LiteralPath $directory.FullName -Directory |
                Where-Object { $_.Name -in @('runs', 'settings') })
            foreach ($dataDirectory in $dataDirectories) {
                if ((Split-Path -Parent $dataDirectory.FullName) -ne $directory.FullName) {
                    $reason = "Nested user data needs manual review: $($dataDirectory.FullName)"
                    break
                }
                foreach ($file in @(Get-ChildItem -Force -Recurse -File -LiteralPath $dataDirectory.FullName -ErrorAction Stop)) {
                    $relative = $file.FullName.Substring($dataDirectory.FullName.Length + 1)
                    $current = Join-Path (Join-Path $package $dataDirectory.Name) $relative
                    Assert-OwnedPath -Path $current -Root $package
                    if (-not (Test-Path -LiteralPath $current -PathType Leaf) -or
                        (Get-PortableFileHash -Path $file.FullName) -ne (Get-PortableFileHash -Path $current)) {
                        $reason = "User data is not already preserved in the current package: $($file.FullName)"
                        break
                    }
                }
                if ($reason) { break }
            }
            if (-not $reason -and $kind -eq 'relocated') {
                $nested = @(Get-ChildItem -Force -Recurse -Directory -LiteralPath $directory.FullName -ErrorAction Stop |
                    Where-Object { $_.Name -in @('runs', 'settings') })
                if ($nested.Count) { $reason = 'Legacy directory contains user data; review manually.' }
            }
            if ($reason) {
                $refused.Add([pscustomobject]@{ Path = $directory.FullName; Reason = $reason })
                continue
            }
            $candidates.Add([pscustomobject]@{
                Path = $directory.FullName; Kind = $kind; Files = $files.Count; Bytes = $bytes
            })
        }

        $result.Candidates = $candidates.ToArray()
        $result.Refused = $refused.ToArray()
        if ($Apply) {
            $removed = New-Object 'System.Collections.Generic.List[object]'
            foreach ($candidate in $candidates) {
                try {
                    Remove-Item -LiteralPath $candidate.Path -Recurse -Force -ErrorAction Stop
                    $removed.Add($candidate)
                    $result.RemovedBytes += [long]$candidate.Bytes
                    $result.RemovedFiles += [int]$candidate.Files
                } catch {
                    $refused.Add([pscustomobject]@{ Path = $candidate.Path; Reason = $_.Exception.Message })
                }
            }
            $result.Removed = $removed.ToArray()
            $result.Refused = $refused.ToArray()
        }
    } catch {
        $result.Error = $_.Exception.Message
        Write-Warning "Stale portable cleanup stopped; remaining files were preserved. $($_.Exception.Message)"
    }
    return $result
}

function Clear-PortableBuildFiles {
    param(
        [string]$Staging,
        [AllowNull()][string]$PreviousPackage,
        [string]$PackagePath,
        [string]$BuildRoot,
        [string]$DistRoot,
        [System.Collections.IDictionary]$PreviousManifest = @{}
    )
    $result = [pscustomobject]@{
        RemovedBytes = [long]0; RemovedFiles = 0
        RetainedPrevious = $PreviousPackage; CleanupSucceeded = $false; Error = $null
    }
    try {
        # Validate every participating tree before the first destructive action.
        foreach ($candidate in @(@{ Path = $Staging; Prefix = 'staging' }, @{ Path = $PreviousPackage; Prefix = 'previous' })) {
            if (-not $candidate.Path) { continue }
            $full = [IO.Path]::GetFullPath($candidate.Path).TrimEnd('\', '/')
            if ((Split-Path -Parent $full).TrimEnd('\', '/') -ne [IO.Path]::GetFullPath($BuildRoot).TrimEnd('\', '/') -or
                (Split-Path -Leaf $full) -notmatch "^$($candidate.Prefix)-\d{8}-\d{6}-\d{3}$") {
                throw "Refusing an unexpected cleanup directory: $full"
            }
            Assert-OwnedPath -Path $full -Root $BuildRoot -InspectTree -RejectMetadata
            if (-not (Test-Path -LiteralPath $full -PathType Container)) {
                throw "Cleanup directory is missing: $full"
            }
        }
        Assert-OwnedPath -Path $PackagePath -Root $DistRoot -InspectTree -RejectMetadata
        if (-not (Test-Path -LiteralPath $PackagePath -PathType Container)) { throw 'Final package is missing.' }
        $stagingFiles = @(Get-ChildItem -Force -Recurse -File -LiteralPath $Staging -ErrorAction Stop)
        $stagingBytes = [long]0
        foreach ($file in $stagingFiles) { $stagingBytes += $file.Length }
        Remove-Item -LiteralPath ([IO.Path]::GetFullPath($Staging)) -Recurse -Force -ErrorAction Stop
        $result.RemovedFiles += $stagingFiles.Count
        $result.RemovedBytes += [long]$stagingBytes
        if ($PreviousPackage) {
            $previousRoot = [IO.Path]::GetFullPath($PreviousPackage).TrimEnd('\', '/')
            foreach ($file in Get-ChildItem -Force -Recurse -File -LiteralPath $previousRoot -ErrorAction Stop) {
                $relative = $file.FullName.Substring($previousRoot.Length + 1).Replace('\', '/')
                $hash = Get-PortableFileHash -Path $file.FullName
                $remove = $false
                if ($relative -match '^(?i:runs|settings)/') {
                    $restored = Join-Path $PackagePath $relative
                    Assert-OwnedPath -Path $restored -Root $PackagePath
                    $remove = (Test-Path -LiteralPath $restored -PathType Leaf) -and
                        ((Get-PortableFileHash -Path $restored) -eq $hash)
                } elseif ($PreviousManifest -and $PreviousManifest.Contains($relative)) {
                    $remove = $PreviousManifest[$relative] -eq $hash
                }
                if ($remove) {
                    Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
                    $result.RemovedFiles++
                    $result.RemovedBytes += $file.Length
                }
            }
            # Deepest first; never recursively remove the backup containing unknown files.
            $directories = @(Get-ChildItem -Force -Recurse -Directory -LiteralPath $previousRoot -ErrorAction Stop |
                Sort-Object { $_.FullName.Length } -Descending)
            foreach ($directory in $directories) {
                if (-not @(Get-ChildItem -Force -LiteralPath $directory.FullName -ErrorAction Stop).Count) {
                    Remove-Item -LiteralPath $directory.FullName -Force -ErrorAction Stop
                }
            }
            if (-not @(Get-ChildItem -Force -LiteralPath $previousRoot -ErrorAction Stop).Count) {
                Remove-Item -LiteralPath $previousRoot -Force -ErrorAction Stop
                $result.RetainedPrevious = $null
            }
        }
        $result.CleanupSucceeded = $true
    } catch {
        $result.Error = $_.Exception.Message
        Write-Warning "Portable build cleanup stopped; remaining files were preserved. $($_.Exception.Message)"
    }
    return $result
}
