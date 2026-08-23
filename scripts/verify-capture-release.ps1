[CmdletBinding()]
param(
    [ValidateSet('All','AC-01','AC-02','AC-03','AC-04','AC-05','AC-06','AC-07','AC-08','AC-09','AC-10','AC-11','AC-12','AC-13','AC-14','AC-15','AC-16','AC-17','AC-18','AC-19','AC-20')]
    [string]$Gate = 'All',
    [string]$PythonPath = '.\.venv\Scripts\python.exe',
    [string]$EvidenceRoot,
    [switch]$Resume,
    [switch]$List
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

$GateNodes = [ordered]@{
    'AC-01' = @('tests/test_capture_activation.py::test_ac_01_route_and_explicit_consent_gate')
    'AC-02' = @('tests/test_recall_activation_gate.py::test_ac_02_lifecycle_and_hard_overview_budget')
    'AC-03' = @('tests/test_capture_scanner.py::test_ac_03_synthetic_seven_day_census_has_full_accounting')
    'AC-04' = @('tests/test_codex_source_adapter.py::test_ac_04_only_completed_main_turns_are_revisions')
    'AC-05' = @('tests/test_capture_hook_latency_script.py::test_exact_1000_samples_and_strict_p95_boundary')
    'AC-06' = @('tests/test_capture_scanner.py::test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources')
    'AC-07' = @('tests/test_capture_capsule_safety.py::test_persistence_gate_returns_stable_zero_to_eight_without_persistent_objects','tests/test_capture_manual_runner.py::test_manual_runner_collects_one_observation_and_settles_actual_usage')
    'AC-08' = @('tests/test_capture_store.py::test_ac_08_two_level_idempotency_and_source_conflict')
    'AC-09' = @('tests/test_capture_transaction.py::test_ac_09_crash_recovery_never_exposes_partial_or_duplicate_batches')
    'AC-10' = @('tests/test_capture_census_end_to_end.py::test_scanner_only_capture_coverage_end_to_end')
    'AC-11' = @('tests/test_capture_read_service.py::test_capture_actions_are_explicit_read_dispatch_routes','tests/test_capture_read_service.py::test_ordinary_recall_actions_do_not_expose_capture_objects')
    'AC-12' = @('tests/test_capture_manual_runner.py::test_one_failed_item_is_settled_and_does_not_block_the_next','tests/test_capture_manual_runner.py::test_transient_source_failure_is_content_free_retryable_with_backoff')
    'AC-13' = @('tests/test_capture_manual_runner.py::test_two_background_workers_enforce_single_concurrency_and_preserve_backlog')
    'AC-14' = @('tests/test_capture_status.py::test_ac_14_pause_exclusions_and_scanner_only_are_diagnosable_and_recoverable')
    'AC-15' = @('tests/test_capture_token_budget.py::test_ac_15_backfill_never_exceeds_actual_or_reserved_ceiling')
    'AC-16' = @('tests/test_capture_read_service.py::test_capture_search_filters_orders_pages_and_redacts_source','tests/test_capture_read_service.py::test_capture_search_orders_fractional_timestamps_and_ties_across_three_pages')
    'AC-17' = @('tests/test_capture_backup_restore.py::test_capture_backup_round_trip_is_allowlisted_and_keeps_recall_isolated')
    'AC-18' = @('tests/test_capture_forget.py::test_observation_capture_forget_rewrites_backups_and_clears_receipt_hashes','tests/test_capture_forget.py::test_revision_capture_forget_leaves_only_content_free_suppression_tombstone')
    'AC-19' = @('tests/test_codex_source_adapter.py::test_ac_19_unknown_formats_fail_closed_without_false_conflicts')
    'AC-20' = @('full-suite','package-build','pip-check','installed-surface','git-diff-check','tracked-text')
}

if ($List) {
    [Console]::OutputEncoding = $Utf8NoBom
    [Console]::Out.WriteLine(($GateNodes | ConvertTo-Json -Depth 4 -Compress))
    exit 0
}

function Get-Sha256File {
    param([string]$PathValue)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [System.IO.File]::OpenRead($PathValue)
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose() }
    }
    finally { $sha.Dispose() }
}

function Quote-ProcessArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Write-Manifest {
    $temporary = $ManifestPath + '.tmp'
    [System.IO.File]::WriteAllText(
        $temporary,
        ($Manifest | ConvertTo-Json -Depth 8 -Compress) + "`n",
        $Utf8NoBom
    )
    Move-Item -LiteralPath $temporary -Destination $ManifestPath -Force
}

function Test-CommandPassed {
    param([string]$GateName, [string]$CommandId)
    return @($Manifest.commands | Where-Object {
        $_.gate -eq $GateName -and $_.command_id -eq $CommandId -and $_.exit_code -eq 0
    }).Count -eq 1
}

function Invoke-RecordedProcess {
    param(
        [string]$GateName,
        [string]$CommandId,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $RepositoryRoot
    )
    $index = $Manifest.commands.Count + 1
    $prefix = '{0:D2}-{1}-{2}' -f $index, $GateName.ToLowerInvariant(), $CommandId
    $stdoutName = $prefix + '.stdout.txt'
    $stderrName = $prefix + '.stderr.txt'
    $stdoutPath = Join-Path $ResolvedEvidence $stdoutName
    $stderrPath = Join-Path $ResolvedEvidence $stderrName
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = (($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join ' ')
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.Result
    $stderr = $stderrTask.Result
    $unsafe = ($stdout + "`n" + $stderr) -match '(?i)PRIVATE_SENTINEL|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY|observation\.statement|source transcript'
    if ($unsafe) {
        $stdout = ''
        $stderr = 'evidence_rejected_content_boundary' + "`n"
        $exitCode = 86
    }
    else { $exitCode = $process.ExitCode }
    [System.IO.File]::WriteAllText($stdoutPath, $stdout, $Utf8NoBom)
    [System.IO.File]::WriteAllText($stderrPath, $stderr, $Utf8NoBom)
    $Manifest.commands += [ordered]@{
        gate = $GateName
        command_id = $CommandId
        exit_code = $exitCode
        stdout_file = $stdoutName
        stdout_sha256 = Get-Sha256File $stdoutPath
        stderr_file = $stderrName
        stderr_sha256 = Get-Sha256File $stderrPath
    }
    Write-Manifest
    return $exitCode
}

$ResolvedPython = if ([System.IO.Path]::IsPathRooted($PythonPath)) {
    [System.IO.Path]::GetFullPath($PythonPath)
} else { [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $PythonPath)) }
if (-not [System.IO.File]::Exists($ResolvedPython)) {
    throw 'PythonPath does not identify a file'
}

if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
    $EvidenceRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('agc-capture-release-' + [Guid]::NewGuid().ToString('N'))
}
$ResolvedEvidence = [System.IO.Path]::GetFullPath($EvidenceRoot)
$ManifestPath = Join-Path $ResolvedEvidence 'manifest.json'
if ($Resume) {
    if (-not [System.IO.File]::Exists($ManifestPath)) { throw 'Resume manifest is unavailable' }
    $loaded = [System.IO.File]::ReadAllText($ManifestPath, $Utf8NoBom) | ConvertFrom-Json
    if ($loaded.schema_version -ne 1 -or $loaded.requested_gate -ne $Gate -or
        $loaded.live_profile_gate -ne 'pending_explicit_authorization') {
        throw 'Resume manifest is invalid'
    }
    $commands = @()
    foreach ($item in @($loaded.commands)) {
        if ($item.gate -notin @($GateNodes.Keys) -or $item.command_id -notmatch '^[a-z0-9-]+$' -or
            $item.exit_code -isnot [int]) { throw 'Resume manifest is invalid' }
        foreach ($stream in @('stdout','stderr')) {
            $name = [string]$item.($stream + '_file')
            if ([System.IO.Path]::GetFileName($name) -ne $name) { throw 'Resume manifest is invalid' }
            $path = Join-Path $ResolvedEvidence $name
            if (-not [System.IO.File]::Exists($path) -or
                (Get-Sha256File $path) -ne [string]$item.($stream + '_sha256')) {
                throw 'Resume evidence hash mismatch'
            }
        }
        $commands += [ordered]@{
            gate = [string]$item.gate; command_id = [string]$item.command_id
            exit_code = [int]$item.exit_code
            stdout_file = [string]$item.stdout_file; stdout_sha256 = [string]$item.stdout_sha256
            stderr_file = [string]$item.stderr_file; stderr_sha256 = [string]$item.stderr_sha256
        }
    }
    if ($commands.Count -gt 0 -and $commands[-1].exit_code -ne 0) {
        if ($commands.Count -eq 1) { $commands = @() }
        else { $commands = @($commands[0..($commands.Count - 2)]) }
    }
    $Manifest = [ordered]@{
        schema_version = 1; requested_gate = $Gate
        live_profile_gate = 'pending_explicit_authorization'
        commands = $commands; status = 'running'
    }
}
else {
    if ([System.IO.Directory]::Exists($ResolvedEvidence) -and (Get-ChildItem -LiteralPath $ResolvedEvidence -Force | Select-Object -First 1)) {
        throw 'EvidenceRoot must be absent or empty'
    }
    [System.IO.Directory]::CreateDirectory($ResolvedEvidence) | Out-Null
    $Manifest = [ordered]@{
        schema_version = 1
        requested_gate = $Gate
        live_profile_gate = 'pending_explicit_authorization'
        commands = @()
        status = 'running'
    }
}
Write-Manifest

$Requested = if ($Gate -eq 'All') { @($GateNodes.Keys) } else { @($Gate) }
$VerificationTempRoot = Join-Path (
    [System.IO.Path]::GetTempPath()
) ('agr-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
[System.IO.Directory]::CreateDirectory($VerificationTempRoot) | Out-Null
$RepositoryUnderTest = $RepositoryRoot
if ('AC-20' -in $Requested) {
    $gitForExport = (Get-Command git -ErrorAction Stop).Source
    $archivePath = Join-Path $VerificationTempRoot 's.zip'
    $RepositoryUnderTest = Join-Path $VerificationTempRoot 's'
    & $gitForExport -C $RepositoryRoot -c core.autocrlf=false archive --format=zip --output=$archivePath HEAD
    if ($LASTEXITCODE -ne 0) { throw 'commit-bound LF export failed' }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $RepositoryUnderTest
    $defaultConfigBytes = [System.IO.File]::ReadAllBytes(
        (Join-Path $RepositoryUnderTest 'agc_runtime\default_config.yaml')
    )
    if (@($defaultConfigBytes | Where-Object { $_ -eq 13 }).Count -ne 0) {
        throw 'LF export contains CR bytes'
    }
}
foreach ($GateName in $Requested) {
    if ($GateName -ne 'AC-20') {
        if (Test-CommandPassed $GateName 'pytest') { continue }
        $temporary = Join-Path $VerificationTempRoot $GateName.ToLowerInvariant()
        $arguments = @('-m','pytest') + @($GateNodes[$GateName]) + @('-q','-p','no:cacheprovider','--basetemp',$temporary)
        $exitCode = Invoke-RecordedProcess $GateName 'pytest' $ResolvedPython $arguments
        if ($exitCode -ne 0) {
            $Manifest.status = 'failed'
            Write-Manifest
            exit $exitCode
        }
        continue
    }

    $fullTemp = Join-Path $VerificationTempRoot 't'
    if (-not (Test-CommandPassed 'AC-20' 'full-suite')) {
        $exitCode = Invoke-RecordedProcess 'AC-20' 'full-suite' $ResolvedPython @('-m','pytest','-q','-p','no:cacheprovider','--basetemp',$fullTemp) -WorkingDirectory $RepositoryUnderTest
        if ($exitCode -ne 0) { $Manifest.status = 'failed'; Write-Manifest; exit $exitCode }
    }
    $packageRoot = Join-Path $ResolvedEvidence 'packages'
    [System.IO.Directory]::CreateDirectory($packageRoot) | Out-Null
    if (-not (Test-CommandPassed 'AC-20' 'package-build')) {
        $exitCode = Invoke-RecordedProcess 'AC-20' 'package-build' $ResolvedPython @('-m','build','--outdir',$packageRoot) -WorkingDirectory $RepositoryUnderTest
        if ($exitCode -ne 0) { $Manifest.status = 'failed'; Write-Manifest; exit $exitCode }
    }
    $wheel = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.whl' -File)
    if ($wheel.Count -ne 1) { $Manifest.status = 'failed'; Write-Manifest; exit 87 }
    $installTarget = Join-Path $ResolvedEvidence 'installed-target'
    if (-not (Test-CommandPassed 'AC-20' 'package-install')) {
        $exitCode = Invoke-RecordedProcess 'AC-20' 'package-install' $ResolvedPython @(
            '-m','pip','install','--no-deps','--target',$installTarget,$wheel[0].FullName
        )
        if ($exitCode -ne 0) { $Manifest.status = 'failed'; Write-Manifest; exit $exitCode }
    }
    $surfaceCheck = @'
import importlib.metadata as metadata
from pathlib import Path
import sys
target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target))
distributions = [item for item in metadata.distributions(path=[str(target)]) if item.metadata.get("Name") == "agent-global-context-runtime"]
if len(distributions) != 1:
    raise SystemExit("distribution located outside isolated target")
distribution = distributions[0]
actual = {item.name: item.value for item in distribution.entry_points if item.group == "console_scripts"}
expected = {
    "agc": "agc_runtime.cli:main",
    "agc-mcp": "agc_runtime.mcp_server:main",
    "agc-capture": "agc_runtime.capture_cli:main",
    "agc-capture-hook": "agc_runtime.capture_hook:main",
}
if actual != expected:
    raise SystemExit("installed entry point surface mismatch")
import agc_runtime
if not Path(agc_runtime.__file__).resolve().is_relative_to(target):
    raise SystemExit("distribution located outside isolated target")
for item in distribution.entry_points:
    if item.group == "console_scripts" and item.name in expected:
        item.load()
print("installed_surface_ok entrypoints=4 version=" + distribution.version)
'@
    if (-not (Test-CommandPassed 'AC-20' 'installed-surface')) {
        $exitCode = Invoke-RecordedProcess 'AC-20' 'installed-surface' $ResolvedPython @('-I','-B','-c',$surfaceCheck,$installTarget)
        if ($exitCode -ne 0) { $Manifest.status = 'failed'; Write-Manifest; exit $exitCode }
    }
    if (-not (Test-CommandPassed 'AC-20' 'pip-check')) {
        $exitCode = Invoke-RecordedProcess 'AC-20' 'pip-check' $ResolvedPython @('-m','pip','check')
        if ($exitCode -ne 0) { $Manifest.status = 'failed'; Write-Manifest; exit $exitCode }
    }
    $git = (Get-Command git -ErrorAction Stop).Source
    if (-not (Test-CommandPassed 'AC-20' 'git-diff-check')) {
        $exitCode = Invoke-RecordedProcess 'AC-20' 'git-diff-check' $git @('diff','--check')
        if ($exitCode -ne 0) { $Manifest.status = 'failed'; Write-Manifest; exit $exitCode }
    }
    $tracked = @(& $git -C $RepositoryRoot ls-files)
    foreach ($relative in $tracked) {
        $path = Join-Path $RepositoryRoot $relative
        if (-not [System.IO.File]::Exists($path)) { continue }
        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        if ($extension -notin @('.py','.ps1','.md','.toml','.yaml','.yml','.json','.txt','.cfg')) { continue }
        $bytes = [System.IO.File]::ReadAllBytes($path)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) { throw 'tracked text contains BOM' }
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        [void]$strictUtf8.GetString($bytes)
    }
    if (-not (Test-CommandPassed 'AC-20' 'tracked-text')) {
        $textPath = Join-Path $ResolvedEvidence 'tracked-text.stdout.txt'
        [System.IO.File]::WriteAllText($textPath, 'tracked_text_utf8_no_bom' + "`n", $Utf8NoBom)
        $emptyPath = Join-Path $ResolvedEvidence 'tracked-text.stderr.txt'
        [System.IO.File]::WriteAllText($emptyPath, '', $Utf8NoBom)
        $Manifest.commands += [ordered]@{
            gate = 'AC-20'; command_id = 'tracked-text'; exit_code = 0
            stdout_file = 'tracked-text.stdout.txt'; stdout_sha256 = Get-Sha256File $textPath
            stderr_file = 'tracked-text.stderr.txt'; stderr_sha256 = Get-Sha256File $emptyPath
        }
        Write-Manifest
    }
}

$Manifest.status = 'passed'
Write-Manifest
[Console]::OutputEncoding = $Utf8NoBom
[Console]::Out.WriteLine(($Manifest | ConvertTo-Json -Depth 8 -Compress))
exit 0
