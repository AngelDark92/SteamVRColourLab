[CmdletBinding()]
param(
    [string]$OutputRoot = $env:COLOURLAB_OUTPUT_ROOT,
    [string]$CurrentEnvironment = '',
    [int]$KeepDays = 7,
    [int]$KeepPrevious = 1,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $OutputRoot) { $OutputRoot = Join-Path (Split-Path -Parent $repoRoot) 'builds\SteamVRColourLab' }
$outputRootPath = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\', '/')
if ($outputRootPath -eq $repoRoot -or
    $outputRootPath.StartsWith("$repoRoot$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase) -or
    $repoRoot.StartsWith("$outputRootPath$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputRoot must be outside the source checkout and must not contain it.'
}

. (Join-Path $PSScriptRoot 'Portable-Cleanup.ps1')
$buildRoot = Join-Path $outputRootPath 'build\portable'
$packagePath = Join-Path $outputRootPath 'dist\SteamVRColourLab'
if (-not $CurrentEnvironment) {
    $sourcePython = Join-Path $outputRootPath '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $sourcePython -PathType Leaf) {
        $version = & $sourcePython -c "import platform; print(platform.python_version())"
        if ($LASTEXITCODE -eq 0) { $CurrentEnvironment = "venv-$version-x64" }
    }
}
$result = Clear-StalePortableBuildFiles -BuildRoot $buildRoot -PackagePath $packagePath `
    -CurrentEnvironment $CurrentEnvironment -KeepDays $KeepDays -KeepPrevious $KeepPrevious -Apply:$Apply

$rows = @($result.Candidates | ForEach-Object {
    [pscustomobject]@{
        Kind = $_.Kind
        Files = $_.Files
        MB = [Math]::Round($_.Bytes / 1MB, 1)
        Path = $_.Path.Substring($buildRoot.Length + 1)
    }
})
if ($rows.Count) {
    Write-Output ''
    Write-Output 'STALE PORTABLE OUTPUT'
    $rows | Format-Table -AutoSize | Out-String | Write-Output
}
foreach ($refused in @($result.Refused)) {
    Write-Output ("KEEP {0} -- {1}" -f $refused.Path.Substring($buildRoot.Length + 1), $refused.Reason)
}
if ($result.Error) {
    Write-Error -Message $result.Error -ErrorAction Continue
    exit 1
}
if ($Apply) {
    Write-Output ("Removed {0} directories, {1} files, {2} MB." -f `
        @($result.Removed).Count, $result.RemovedFiles, [Math]::Round($result.RemovedBytes / 1MB, 1))
} else {
    $candidateFiles = 0
    $candidateBytes = [long]0
    foreach ($candidate in @($result.Candidates)) {
        $candidateFiles += [int]$candidate.Files
        $candidateBytes += [long]$candidate.Bytes
    }
    Write-Output ("Preview: {0} directories, {1} files, {2} MB. Add -Apply to delete." -f `
        $rows.Count, $candidateFiles, [Math]::Round($candidateBytes / 1MB, 1))
}
$receipt = Join-Path $buildRoot $(if ($Apply) { 'stale-cleanup-manual.json' } else { 'stale-preview.json' })
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt -Encoding UTF8
