[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Launcher,
    [Parameter(Mandatory = $true)] [string]$MemoryRoot,
    [Parameter(Mandatory = $true)] [string]$RuntimePath,
    [Parameter(Mandatory = $true)] [string]$OutputPath,
    [ValidateRange(1, 10000)] [int]$Samples = 1000
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Full-Path([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { exit 2 }
    try { return [System.IO.Path]::GetFullPath($Value) }
    catch { exit 2 }
}

function File-Hash([string]$PathValue) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [System.IO.File]::OpenRead($PathValue)
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose() }
    }
    finally { $sha.Dispose() }
}

function Percentile([double[]]$Sorted, [double]$Fraction) {
    $index = [Math]::Ceiling($Fraction * $Sorted.Count) - 1
    if ($index -lt 0) { $index = 0 }
    return $Sorted[$index]
}

function Median([double[]]$Sorted) {
    $middle = [int][Math]::Floor($Sorted.Count / 2)
    if (($Sorted.Count % 2) -eq 1) { return $Sorted[$middle] }
    return ($Sorted[$middle - 1] + $Sorted[$middle]) / 2.0
}

function Write-AtomicReport([string]$Target, [string]$Content) {
    $parent = [System.IO.Path]::GetDirectoryName($Target)
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    $temporary = Join-Path $parent ('.agc-latency-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [System.IO.File]::WriteAllText($temporary, $Content, $Utf8NoBom)
        Move-Item -LiteralPath $temporary -Destination $Target -Force
    }
    finally {
        if ([System.IO.File]::Exists($temporary)) { Remove-Item -LiteralPath $temporary -Force }
    }
}

$launcherPath = Full-Path $Launcher
$memoryPath = Full-Path $MemoryRoot
$runtimeFile = Full-Path $RuntimePath
$reportPath = Full-Path $OutputPath
if (-not [System.IO.File]::Exists($launcherPath) -or -not [System.IO.File]::Exists($runtimeFile)) { exit 2 }

$payload = [Console]::In.ReadToEnd()
$dirtyRoot = Join-Path $memoryPath '.runtime\capture\dirty'
$markersBefore = @{}
if ([System.IO.Directory]::Exists($dirtyRoot)) {
    foreach ($item in Get-ChildItem -LiteralPath $dirtyRoot -File -Force) { $markersBefore[$item.FullName] = $true }
}

$timings = New-Object System.Collections.Generic.List[double]
$failureCount = 0
$testValues = $null
if (-not [string]::IsNullOrWhiteSpace($env:AGC_CAPTURE_TEST_SAMPLE_MS)) {
    try {
        $testValues = @($env:AGC_CAPTURE_TEST_SAMPLE_MS.Split(',') | ForEach-Object {
            [double]::Parse($_, [System.Globalization.CultureInfo]::InvariantCulture)
        })
    }
    catch { exit 2 }
    if ($testValues.Count -ne $Samples) { exit 2 }
}

try {
    for ($index = 0; $index -lt $Samples; $index += 1) {
        if ($null -ne $testValues) {
            $timings.Add($testValues[$index])
            continue
        }
        $start = [System.Diagnostics.Stopwatch]::GetTimestamp()
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $launcherPath
        $info.Arguments = '--root "' + $memoryPath + '"'
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardInput = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $info
        try {
            if (-not $process.Start()) { throw 'process did not start' }
            $process.StandardInput.Write($payload)
            $process.StandardInput.Close()
            $stdout = $process.StandardOutput.ReadToEnd()
            $stderr = $process.StandardError.ReadToEnd()
            $process.WaitForExit()
            if ($process.ExitCode -ne 0 -or $stdout.Length -ne 0 -or $stderr.Length -ne 0) { $failureCount += 1 }
        }
        catch { $failureCount += 1 }
        finally { $process.Dispose() }
        $elapsed = (([System.Diagnostics.Stopwatch]::GetTimestamp() - $start) * 1000.0) / [System.Diagnostics.Stopwatch]::Frequency
        $timings.Add([Math]::Round($elapsed, 3))
    }
}
finally {
    if ([System.IO.Directory]::Exists($dirtyRoot)) {
        foreach ($item in Get-ChildItem -LiteralPath $dirtyRoot -File -Force) {
            if (-not $markersBefore.ContainsKey($item.FullName)) { Remove-Item -LiteralPath $item.FullName -Force }
        }
    }
}

$sorted = [double[]]@($timings | Sort-Object)
$p95 = [Math]::Round((Percentile $sorted 0.95), 3)
$passed = $Samples -eq 1000 -and $failureCount -eq 0 -and $p95 -lt 100.0
$report = [ordered]@{
    schema_version = 1
    sample_count = $Samples
    cold_sample_count = [Math]::Min(10, $Samples)
    warm_sample_count = [Math]::Max(0, $Samples - 10)
    min_ms = [Math]::Round($sorted[0], 3)
    median_ms = [Math]::Round((Median $sorted), 3)
    p95_ms = $p95
    max_ms = [Math]::Round($sorted[-1], 3)
    failure_count = $failureCount
    launcher_sha256 = File-Hash $launcherPath
    runtime_sha256 = File-Hash $runtimeFile
    powershell_version = $PSVersionTable.PSVersion.ToString()
    os_version = [Environment]::OSVersion.VersionString
    passed = $passed
}
Write-AtomicReport $reportPath ($report | ConvertTo-Json -Depth 6 -Compress)
if ($passed) { exit 0 }
exit 1
