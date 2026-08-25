[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Status', 'EnableScanner', 'EnableHook', 'EnableRunner', 'Pause', 'Disable', 'Rollback')]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$CodexHome,

    [Parameter(Mandatory = $true)]
    [string]$MemoryRoot,

    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,

    [string]$ExpectedActivationDigest,

    [string]$ActivationEvidencePath,

    [ValidateRange(1, 1440)]
    [int]$ScheduleMinutes = 15,

    [int]$IncrementalTokenBudget = 0,

    [string]$LatencyReportPath,

    [string]$ExpectedLatencyReportHash
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Envelope {
    param(
        [string]$Status,
        [hashtable]$Data,
        [hashtable]$ErrorValue,
        [int]$ExitCode
    )
    $envelope = [ordered]@{
        schema_version = 1
        action = $Action
        status = $Status
        data = if ($null -eq $Data) { @{} } else { $Data }
        error = $ErrorValue
    }
    [Console]::OutputEncoding = $Utf8NoBom
    [Console]::Out.WriteLine(($envelope | ConvertTo-Json -Depth 12 -Compress))
    exit $ExitCode
}

function Fail-HostConfig {
    param([string]$Code, [string]$Message)
    Write-Envelope -Status 'failed' -Data @{} -ErrorValue ([ordered]@{
        code = $Code
        message = $Message
    }) -ExitCode 2
}

function Get-FullPath {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Fail-HostConfig 'invalid_host_path' 'Host path is invalid'
    }
    try {
        return [System.IO.Path]::GetFullPath($Value).TrimEnd('\', '/')
    }
    catch {
        Fail-HostConfig 'invalid_host_path' 'Host path is invalid'
    }
}

function Test-PathOverlap {
    param([string]$Left, [string]$Right)
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    if ([string]::Equals($Left, $Right, $comparison)) { return $true }
    $leftPrefix = $Left + [System.IO.Path]::DirectorySeparatorChar
    $rightPrefix = $Right + [System.IO.Path]::DirectorySeparatorChar
    return $Left.StartsWith($rightPrefix, $comparison) -or $Right.StartsWith($leftPrefix, $comparison)
}

function Test-ReparseAncestor {
    param([string]$PathValue)
    $current = $PathValue
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if ([System.IO.Directory]::Exists($current) -or [System.IO.File]::Exists($current)) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                return $true
            }
        }
        $parent = [System.IO.Path]::GetDirectoryName($current)
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
    return $false
}

function Get-Sha256Text {
    param([string]$Value)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $Utf8NoBom.GetBytes($Value)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-Sha256FileOrAbsent {
    param([string]$PathValue)
    if (-not [System.IO.File]::Exists($PathValue)) { return 'absent' }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [System.IO.File]::OpenRead($PathValue)
        try {
            return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $stream.Dispose()
        }
    }
    finally {
        $sha.Dispose()
    }
}

$codexPath = Get-FullPath $CodexHome
$memoryPath = Get-FullPath $MemoryRoot
$installPath = Get-FullPath $InstallRoot

if (-not [System.IO.Directory]::Exists($codexPath) -or -not [System.IO.Directory]::Exists($installPath)) {
    Fail-HostConfig 'host_path_missing' 'Required Host path is missing'
}
if ((Test-PathOverlap $codexPath $memoryPath) -or
    (Test-PathOverlap $installPath $memoryPath) -or
    (Test-PathOverlap $codexPath $installPath)) {
    Fail-HostConfig 'host_path_overlap' 'Host paths must not overlap'
}
if ((Test-ReparseAncestor $codexPath) -or (Test-ReparseAncestor $memoryPath) -or (Test-ReparseAncestor $installPath)) {
    Fail-HostConfig 'host_path_reparse' 'Host paths must not traverse reparse points'
}

$captureLauncher = Join-Path $installPath 'bin\agc-capture.cmd'
$hookLauncher = Join-Path $installPath 'bin\agc-capture-hook.cmd'
if (-not [System.IO.File]::Exists($captureLauncher) -or -not [System.IO.File]::Exists($hookLauncher)) {
    Fail-HostConfig 'capture_launcher_missing' 'Capture launcher is missing'
}

$memoryRootId = Get-Sha256Text $memoryPath.ToLowerInvariant()
$taskName = 'AgentGlobalContext-Capture-' + $memoryRootId.Substring(0, 12)
$planMaterial = @(
    'capture-host-plan-v1',
    $memoryRootId,
    (Get-Sha256Text $codexPath.ToLowerInvariant()),
    (Get-Sha256FileOrAbsent (Join-Path $codexPath 'config.toml')),
    (Get-Sha256FileOrAbsent (Join-Path $codexPath 'hooks.json')),
    (Get-Sha256FileOrAbsent $captureLauncher),
    (Get-Sha256FileOrAbsent $hookLauncher),
    (Get-Sha256FileOrAbsent (Join-Path $memoryPath 'config.yaml')),
    (Get-Sha256FileOrAbsent $env:AGC_CAPTURE_SCHEDULER_STATE),
    $ScheduleMinutes.ToString([System.Globalization.CultureInfo]::InvariantCulture)
) -join "`n"
$hostStateDigest = Get-Sha256Text $planMaterial

if ([string]::IsNullOrWhiteSpace($ActivationEvidencePath)) {
    Fail-HostConfig 'activation_evidence_required' 'Content-free activation evidence is required'
}
$evidencePath = Get-FullPath $ActivationEvidencePath
if (-not [System.IO.File]::Exists($evidencePath) -or (Test-ReparseAncestor $evidencePath)) {
    Fail-HostConfig 'activation_evidence_invalid' 'Activation evidence is invalid'
}
try {
    $activationOutput = @(& $captureLauncher 'activation' '--root' $memoryPath '--evidence' $evidencePath 2>$null)
    $activationExitCode = $LASTEXITCODE
    if ($activationExitCode -ne 0 -or $activationOutput.Count -ne 1) { throw 'invalid activation response' }
    $activationResponse = $activationOutput[0] | ConvertFrom-Json
    if ($activationResponse.status -ne 'accepted' -or
        $activationResponse.action -ne 'activation' -or
        $activationResponse.data.activation_digest -notmatch '^[0-9a-f]{64}$') {
        throw 'invalid activation response'
    }
}
catch {
    Fail-HostConfig 'activation_evidence_invalid' 'Activation evidence is invalid'
}
$activationDigest = [string]$activationResponse.data.activation_digest

if ($Action -eq 'Status') {
    Write-Envelope -Status 'accepted' -Data ([ordered]@{
        mutation_performed = $false
        task_name = $taskName
        activation_digest = $activationDigest
        host_state_digest = $hostStateDigest
        route_assessment = [string]$activationResponse.data.route_assessment
        readiness = $activationResponse.data.readiness
        schedule_minutes = $ScheduleMinutes
        hook_definition_assessment = if ([System.IO.File]::Exists((Join-Path $codexPath 'hooks.json'))) { 'present' } else { 'absent' }
        scheduler_assessment = 'not_assessed'
    }) -ErrorValue $null -ExitCode 0
}

if ([string]::IsNullOrWhiteSpace($ExpectedActivationDigest)) {
    Fail-HostConfig 'activation_digest_required' 'Exact activation digest is required'
}
if ($ExpectedActivationDigest -notmatch '^[0-9a-f]{64}$' -or
    -not [string]::Equals($ExpectedActivationDigest, $activationDigest, [System.StringComparison]::Ordinal)) {
    Fail-HostConfig 'activation_digest_mismatch' 'Activation digest does not match current Host state'
}

if ($activationResponse.data.route_assessment -ne 'ready') {
    Fail-HostConfig 'activation_route_not_ready' 'Capture route is not ready'
}
if ($Action -eq 'EnableScanner' -and $activationResponse.data.evidence.recall_gate_passed -ne $true) {
    Fail-HostConfig 'recall_gate_required' 'Recall Gate evidence is required'
}
if ($Action -eq 'EnableHook' -and $activationResponse.data.readiness.scanner_ready -ne $true) {
    Fail-HostConfig 'scanner_readiness_required' 'Scanner readiness is required'
}
if ($Action -eq 'EnableRunner' -and $activationResponse.data.readiness.backfill_runner_ready -ne $true) {
    Fail-HostConfig 'extractor_capability_required' 'Extractor capability and frozen Census are required'
}

function Write-AtomicUtf8 {
    param([string]$Target, [string]$Content)
    $parent = [System.IO.Path]::GetDirectoryName($Target)
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    $temporary = Join-Path $parent ('.agc-host-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [System.IO.File]::WriteAllText($temporary, $Content, $Utf8NoBom)
        Move-Item -LiteralPath $temporary -Destination $Target -Force
    }
    finally {
        if ([System.IO.File]::Exists($temporary)) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function New-BackupManifest {
    param([string[]]$Targets)
    $backupRoot = Join-Path $installPath 'backups\capture-host'
    [System.IO.Directory]::CreateDirectory($backupRoot) | Out-Null
    $backupDirectory = Join-Path $backupRoot ((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ') + '-' + [Guid]::NewGuid().ToString('N'))
    [System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
    $items = @()
    $index = 0
    foreach ($target in $Targets) {
        if ([string]::IsNullOrWhiteSpace($target)) { continue }
        $name = ('before-{0:D3}.bin' -f $index)
        $existed = [System.IO.File]::Exists($target)
        if ($existed) {
            [System.IO.File]::Copy($target, (Join-Path $backupDirectory $name), $false)
        }
        $items += [ordered]@{ target = $target; existed = $existed; backup = $name }
        $index += 1
    }
    $manifest = [ordered]@{ schema_version = 1; action = $Action; items = $items }
    Write-AtomicUtf8 (Join-Path $backupDirectory 'manifest.json') ($manifest | ConvertTo-Json -Depth 8 -Compress)
    return $backupDirectory
}

function Restore-BackupManifest {
    param([string]$BackupDirectory)
    $manifestPath = Join-Path $BackupDirectory 'manifest.json'
    if (-not [System.IO.File]::Exists($manifestPath)) {
        throw 'backup manifest is missing'
    }
    $manifest = [System.IO.File]::ReadAllText($manifestPath, $Utf8NoBom) | ConvertFrom-Json
    foreach ($item in @($manifest.items)) {
        if ($item.existed) {
            $parent = [System.IO.Path]::GetDirectoryName([string]$item.target)
            [System.IO.Directory]::CreateDirectory($parent) | Out-Null
            [System.IO.File]::Copy((Join-Path $BackupDirectory ([string]$item.backup)), ([string]$item.target), $true)
        }
        elseif ([System.IO.File]::Exists([string]$item.target)) {
            Remove-Item -LiteralPath ([string]$item.target) -Force
        }
    }
    if ([string]::IsNullOrWhiteSpace($env:AGC_CAPTURE_SCHEDULER_STATE)) {
        $schedulerBackup = Join-Path $BackupDirectory 'scheduler-before.xml'
        if ([System.IO.File]::Exists($schedulerBackup)) {
            Register-ScheduledTask -TaskName $taskName -Xml ([System.IO.File]::ReadAllText($schedulerBackup, $Utf8NoBom)) -Force | Out-Null
        }
        else {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
}

function Get-LatestCommittedBackup {
    $backupRoot = Join-Path $installPath 'backups\capture-host'
    if (-not [System.IO.Directory]::Exists($backupRoot)) { return $null }
    return Get-ChildItem -LiteralPath $backupRoot -Directory |
        Where-Object { [System.IO.File]::Exists((Join-Path $_.FullName 'committed')) } |
        Sort-Object Name -Descending |
        Select-Object -First 1
}

function Get-DefaultConfig {
    $sourceJson = $codexPath | ConvertTo-Json -Compress
    return @"
schema_version: 3
sensitive_storage: disabled
recall:
  overview_token_budget: 250
  compact_card_token_budget: 600
  default_lifecycle: active
capture:
  schema_version: 1
  enabled: true
  mode: scanner_only
  paused: false
  include_subagents: false
  sources:
    - $sourceJson
  hook:
    enabled: false
  runner:
    concurrency: 1
    max_attempts: 5
    backoff_seconds: [60, 300, 1800, 7200, 21600]
  capsule:
    target_tokens: 1200
    max_tokens: 3000
  budgets:
    backfill_window_days: 7
    backfill_total_tokens: 100000
    incremental_total_tokens: null
  extractor:
    kind: codex_exec
    executable: codex
    model: null
  exclude:
    task_ids: []
    project_ids: []
"@
}

function Enable-ScannerConfig {
    param([string]$ConfigPath)
    if (-not [System.IO.File]::Exists($ConfigPath)) {
        Write-AtomicUtf8 $ConfigPath (Get-DefaultConfig)
        return
    }
    $text = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom)
    $text = [regex]::Replace($text, '(?m)^  enabled: [^\r\n]+(?=\r?$)', '  enabled: true')
    $text = [regex]::Replace($text, '(?m)^  mode: [^\r\n]+(?=\r?$)', '  mode: scanner_only')
    $text = [regex]::Replace($text, '(?m)^  paused: [^\r\n]+(?=\r?$)', '  paused: false')
    if ($text -match '(?m)^  sources: \[\]$') {
        $sourceJson = $codexPath | ConvertTo-Json -Compress
        $text = [regex]::Replace($text, '(?m)^  sources: \[\]$', "  sources:`n    - $sourceJson")
    }
    Write-AtomicUtf8 $ConfigPath $text
}

function Set-HookEnabled {
    param([string]$ConfigPath)
    $text = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom)
    $text = [regex]::Replace($text, '(?m)^    enabled: [^\r\n]+(?=\r?$)', '    enabled: true', 1)
    Write-AtomicUtf8 $ConfigPath $text
}

function Set-ConfigState {
    param(
        [string]$ConfigPath,
        [bool]$Enabled,
        [string]$Mode,
        [bool]$Paused,
        [object]$Budget,
        [object]$HookEnabled
    )
    $text = [System.IO.File]::ReadAllText($ConfigPath, $Utf8NoBom)
    $text = [regex]::Replace($text, '(?m)^  enabled: [^\r\n]+(?=\r?$)', ('  enabled: ' + $Enabled.ToString().ToLowerInvariant()))
    $text = [regex]::Replace($text, '(?m)^  mode: [^\r\n]+(?=\r?$)', ('  mode: ' + $Mode))
    $text = [regex]::Replace($text, '(?m)^  paused: [^\r\n]+(?=\r?$)', ('  paused: ' + $Paused.ToString().ToLowerInvariant()))
    if ($null -ne $Budget) {
        $text = [regex]::Replace($text, '(?m)^    incremental_total_tokens: [^\r\n]+(?=\r?$)', ('    incremental_total_tokens: ' + [int]$Budget))
    }
    if ($null -ne $HookEnabled) {
        $replacement = '    enabled: ' + ([bool]$HookEnabled).ToString().ToLowerInvariant()
        $text = [regex]::Replace($text, '(?m)^    enabled: [^\r\n]+(?=\r?$)', $replacement, 1)
    }
    Write-AtomicUtf8 $ConfigPath $text
}

function Set-SchedulerState {
    param([ValidateSet('scanner', 'runner')][string]$Mode)
    $arguments = 'cycle --root "' + $memoryPath + '" --once'
    if ($Mode -eq 'runner') {
        $arguments += ' --max-items 10'
    }
    $state = [ordered]@{
        schema_version = 1
        task_name = $taskName
        command = $captureLauncher
        arguments = $arguments
        multiple_instances = 'IgnoreNew'
        start_when_available = $true
        triggers = @('logon', ('repetition:' + $ScheduleMinutes + 'm'))
    }
    if (-not [string]::IsNullOrWhiteSpace($env:AGC_CAPTURE_SCHEDULER_STATE)) {
        Write-AtomicUtf8 $env:AGC_CAPTURE_SCHEDULER_STATE ($state | ConvertTo-Json -Depth 8 -Compress)
        return
    }
    $userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $interval = 'PT' + $ScheduleMinutes + 'M'
    $startBoundary = (Get-Date).AddMinutes(1).ToString('yyyy-MM-ddTHH:mm:ss')
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Agent Global Context Capture one-shot cycle</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
    <TimeTrigger><Repetition><Interval>$interval</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>$startBoundary</StartBoundary><Enabled>true</Enabled></TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>$([System.Security.SecurityElement]::Escape($userId))</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><Enabled>true</Enabled><ExecutionTimeLimit>PT30M</ExecutionTimeLimit></Settings>
  <Actions Context="Author"><Exec><Command>$([System.Security.SecurityElement]::Escape($captureLauncher))</Command><Arguments>$([System.Security.SecurityElement]::Escape($arguments))</Arguments></Exec></Actions>
</Task>
"@
    Register-ScheduledTask -TaskName $taskName -Xml $xml -Force -ErrorAction Stop | Out-Null
}

function Merge-OwnedHook {
    param([string]$HooksPath)
    if ([System.IO.File]::Exists($HooksPath)) {
        try {
            $document = [System.IO.File]::ReadAllText($HooksPath, $Utf8NoBom) | ConvertFrom-Json
        }
        catch {
            Fail-HostConfig 'invalid_hooks_json' 'Hooks configuration is invalid'
        }
    }
    else {
        $document = [pscustomobject]@{}
    }
    if ($null -eq $document.Stop) {
        $document | Add-Member -NotePropertyName Stop -NotePropertyValue @()
    }
    $ownedNeedle = 'agc-capture-hook.cmd'
    $command = '"' + $hookLauncher + '" --root "' + $memoryPath + '"'
    foreach ($candidate in @($document.Stop | Where-Object {
        (($_.commandWindows -is [string]) -and $_.commandWindows.Contains($ownedNeedle)) -or
        (($_.command -is [string]) -and $_.command.Contains($ownedNeedle))
    })) {
        if ($candidate.type -ne 'command' -or
            $candidate.command -ne $command -or
            $candidate.commandWindows -ne $command -or
            $candidate.async -ne $true -or
            $candidate.timeout -ne 5) {
            Fail-HostConfig 'conflicting_capture_hook' 'An unknown Capture Hook definition already exists'
        }
    }
    $others = @($document.Stop | Where-Object {
        -not (($_.commandWindows -is [string]) -and $_.commandWindows.Contains($ownedNeedle))
    })
    $owned = [ordered]@{
        type = 'command'
        command = $command
        commandWindows = $command
        async = $true
        timeout = 5
    }
    $document.Stop = @($others) + @($owned)
    Write-AtomicUtf8 $HooksPath ($document | ConvertTo-Json -Depth 20)
}

function Remove-OwnedHook {
    param([string]$HooksPath)
    if (-not [System.IO.File]::Exists($HooksPath)) { return }
    try {
        $document = [System.IO.File]::ReadAllText($HooksPath, $Utf8NoBom) | ConvertFrom-Json
    }
    catch {
        Fail-HostConfig 'invalid_hooks_json' 'Hooks configuration is invalid'
    }
    if ($null -ne $document.Stop) {
        $document.Stop = @($document.Stop | Where-Object {
            -not (($_.commandWindows -is [string]) -and $_.commandWindows.Contains('agc-capture-hook.cmd'))
        })
    }
    Write-AtomicUtf8 $HooksPath ($document | ConvertTo-Json -Depth 20)
}

function Remove-SchedulerState {
    if (-not [string]::IsNullOrWhiteSpace($env:AGC_CAPTURE_SCHEDULER_STATE)) {
        if ([System.IO.File]::Exists($env:AGC_CAPTURE_SCHEDULER_STATE)) {
            Remove-Item -LiteralPath $env:AGC_CAPTURE_SCHEDULER_STATE -Force
        }
        return
    }
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    catch {
        throw 'scheduled task removal failed'
    }
}

$configPath = Join-Path $memoryPath 'config.yaml'
$hooksPath = Join-Path $codexPath 'hooks.json'
$schedulerPath = $env:AGC_CAPTURE_SCHEDULER_STATE

if ($Action -eq 'EnableRunner' -and $IncrementalTokenBudget -le 0) {
    Fail-HostConfig 'incremental_budget_required' 'A positive incremental token budget is required'
}

if ($Action -eq 'Rollback') {
    $latest = Get-LatestCommittedBackup
    if ($null -eq $latest) {
        Fail-HostConfig 'rollback_unavailable' 'No committed Host backup is available'
    }
    try {
        Restore-BackupManifest $latest.FullName
        [System.IO.File]::WriteAllText((Join-Path $latest.FullName 'rolled_back'), '1', $Utf8NoBom)
        Remove-Item -LiteralPath (Join-Path $latest.FullName 'committed') -Force
    }
    catch {
        Write-Envelope -Status 'failed' -Data @{} -ErrorValue ([ordered]@{
            code = 'rollback_failed'; message = 'Host rollback failed'
        }) -ExitCode 1
    }
    Write-Envelope -Status 'accepted' -Data ([ordered]@{
        code = 'host_rollback_complete'; mutation_performed = $true
        backup_id = $latest.Name
    }) -ErrorValue $null -ExitCode 0
}

if ($Action -eq 'EnableHook') {
    if ([string]::IsNullOrWhiteSpace($LatencyReportPath) -or [string]::IsNullOrWhiteSpace($ExpectedLatencyReportHash)) {
        Fail-HostConfig 'latency_report_required' 'A verified Hook latency report is required'
    }
    $latencyPath = Get-FullPath $LatencyReportPath
    if (-not [System.IO.File]::Exists($latencyPath) -or
        -not $latencyPath.StartsWith($installPath + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
        (Test-ReparseAncestor $latencyPath)) {
        Fail-HostConfig 'latency_report_invalid' 'Hook latency report is invalid'
    }
    $actualLatencyHash = Get-Sha256FileOrAbsent $latencyPath
    if ($ExpectedLatencyReportHash -notmatch '^[0-9a-f]{64}$' -or
        -not [string]::Equals($ExpectedLatencyReportHash, $actualLatencyHash, [System.StringComparison]::Ordinal)) {
        Fail-HostConfig 'latency_report_hash_mismatch' 'Hook latency report hash does not match'
    }
    try {
        $latency = [System.IO.File]::ReadAllText($latencyPath, $Utf8NoBom) | ConvertFrom-Json
    }
    catch {
        Fail-HostConfig 'latency_report_invalid' 'Hook latency report is invalid'
    }
    $launcherHash = Get-Sha256FileOrAbsent $hookLauncher
    if ($latency.schema_version -ne 1 -or
        $latency.sample_count -lt 1000 -or
        $latency.p95_ms -ge 100 -or
        $latency.passed -ne $true -or
        $latency.launcher_sha256 -ne $launcherHash) {
        Fail-HostConfig 'latency_gate_failed' 'Hook latency gate did not pass'
    }
    $inlineConfig = Join-Path $codexPath 'config.toml'
    if ([System.IO.File]::Exists($inlineConfig)) {
        $inlineText = [System.IO.File]::ReadAllText($inlineConfig, $Utf8NoBom)
        if ($inlineText -match '(?im)^\s*(hooks_enabled|experimental_use_hooks)\s*=\s*false\s*$') {
            Fail-HostConfig 'hooks_disabled_by_policy' 'Hooks are disabled by policy'
        }
    }
    if ([System.IO.File]::Exists($hooksPath)) {
        try { [void]([System.IO.File]::ReadAllText($hooksPath, $Utf8NoBom) | ConvertFrom-Json) }
        catch { Fail-HostConfig 'invalid_hooks_json' 'Hooks configuration is invalid' }
    }
}

$backup = New-BackupManifest @($configPath, $hooksPath, $schedulerPath)
if ([string]::IsNullOrWhiteSpace($env:AGC_CAPTURE_SCHEDULER_STATE)) {
    try {
        $previousTask = Export-ScheduledTask -TaskName $taskName -ErrorAction Stop
        Write-AtomicUtf8 (Join-Path $backup 'scheduler-before.xml') $previousTask
    }
    catch [Microsoft.Management.Infrastructure.CimException] {
        # Absence is a valid before-image.
    }
}

function Complete-HostAction {
    param([string]$Code, [hashtable]$Extra)
    [System.IO.File]::WriteAllText((Join-Path $backup 'committed'), '1', $Utf8NoBom)
    $data = [ordered]@{ code = $Code; mutation_performed = $true; backup_id = [System.IO.Path]::GetFileName($backup) }
    foreach ($key in $Extra.Keys) { $data[$key] = $Extra[$key] }
    Write-Envelope -Status 'accepted' -Data $data -ErrorValue $null -ExitCode 0
}

function Invoke-Injection {
    param([string]$Boundary)
    if ($env:AGC_CAPTURE_INJECT_FAILURE -eq $Boundary) {
        throw 'injected host mutation failure'
    }
}

try {

if ($Action -eq 'EnableScanner') {
    Enable-ScannerConfig $configPath
    Invoke-Injection 'after_config'
    Set-SchedulerState -Mode 'scanner'
    Invoke-Injection 'after_scheduler'
    Complete-HostAction 'scanner_enabled' @{ task_name = $taskName }
}

if ($Action -eq 'EnableHook') {
    if (-not [System.IO.File]::Exists($configPath)) {
        Fail-HostConfig 'scanner_not_enabled' 'Scanner must be enabled first'
    }
    Merge-OwnedHook $hooksPath
    Invoke-Injection 'after_hooks'
    Set-HookEnabled $configPath
    Invoke-Injection 'after_config'
    Complete-HostAction 'hook_definition_staged' @{ trust_required = $true }
}

if ($Action -eq 'EnableRunner') {
    if (-not [System.IO.File]::Exists($configPath)) {
        Fail-HostConfig 'scanner_not_enabled' 'Scanner must be enabled first'
    }
    Set-ConfigState $configPath $true 'runner' $false $IncrementalTokenBudget $null
    Invoke-Injection 'after_config'
    Set-SchedulerState -Mode 'runner'
    Invoke-Injection 'after_scheduler'
    Complete-HostAction 'runner_enabled' @{}
}

if ($Action -eq 'Pause') {
    if (-not [System.IO.File]::Exists($configPath)) {
        Fail-HostConfig 'capture_not_configured' 'Capture is not configured'
    }
    $existing = [System.IO.File]::ReadAllText($configPath, $Utf8NoBom)
    $mode = if ($existing -match '(?m)^  mode: ([^\r\n]+)$') { $Matches[1].Trim() } else { 'scanner_only' }
    Set-ConfigState $configPath $true $mode $true $null $null
    Invoke-Injection 'after_config'
    Complete-HostAction 'capture_paused' @{}
}

if ($Action -eq 'Disable') {
    if (-not [System.IO.File]::Exists($configPath)) {
        Fail-HostConfig 'capture_not_configured' 'Capture is not configured'
    }
    Set-ConfigState $configPath $false 'off' $false $null $false
    Invoke-Injection 'after_config'
    Remove-OwnedHook $hooksPath
    Invoke-Injection 'after_hooks'
    Remove-SchedulerState
    Invoke-Injection 'after_scheduler'
    Complete-HostAction 'capture_disabled' @{}
}

Fail-HostConfig 'host_action_invalid_state' 'Host action could not be applied'
}
catch {
    try {
        Restore-BackupManifest $backup
        [System.IO.File]::WriteAllText((Join-Path $backup 'rolled_back'), '1', $Utf8NoBom)
    }
    catch {
        Write-Envelope -Status 'failed' -Data @{} -ErrorValue ([ordered]@{
            code = 'host_rollback_failed'; message = 'Host mutation and rollback failed'
        }) -ExitCode 1
    }
    Write-Envelope -Status 'failed' -Data @{} -ErrorValue ([ordered]@{
        code = 'host_mutation_failed'; message = 'Host mutation failed and was rolled back'
    }) -ExitCode 1
}
