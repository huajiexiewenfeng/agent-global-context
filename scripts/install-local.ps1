[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepositoryRoot,
    [Parameter(Mandatory=$true)][string]$SkillsRoot,
    [Parameter(Mandatory=$true)][string]$CodexConfig,
    [Parameter(Mandatory=$true)][string]$MemoryRoot,
    [string]$InstallRoot = "$env:USERPROFILE\.agent-global-context-runtime",
    [switch]$SkipRuntimeInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BeginMarker = "# BEGIN agent-global-context"
$EndMarker = "# END agent-global-context"
$PublicSkillName = "agent-global-context"
$RetiredSkillNames = @(
    "agent-global-context-recall",
    "agent-global-context-commit",
    "agent-global-context-capture",
    "agent-global-context-review"
)
$StrictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
$WriteUtf8 = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $WriteUtf8
[Console]::OutputEncoding = $WriteUtf8

function Get-ExistingDirectoryPath {
    param([string]$Path, [string]$Label)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Label must be an existing directory: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-ExistingFilePath {
    param([string]$Path, [string]$Label)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label must be an existing file: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-AbsolutePath {
    param([string]$Path, [string]$Label)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label must not be empty."
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $fullPath) {
        return (Resolve-Path -LiteralPath $fullPath).Path
    }

    $segments = New-Object System.Collections.Generic.List[string]
    $existingAncestor = $fullPath
    while (-not (Test-Path -LiteralPath $existingAncestor)) {
        $leaf = [System.IO.Path]::GetFileName($existingAncestor)
        if ([string]::IsNullOrEmpty($leaf)) {
            throw "$Label does not have a resolvable existing ancestor: $Path"
        }
        $segments.Insert(0, $leaf)
        $parent = [System.IO.Path]::GetDirectoryName($existingAncestor)
        if ([string]::IsNullOrEmpty($parent)) {
            throw "$Label does not have a resolvable existing ancestor: $Path"
        }
        $existingAncestor = $parent
    }
    $canonical = (Resolve-Path -LiteralPath $existingAncestor).Path
    foreach ($segment in $segments) {
        $canonical = Join-Path $canonical $segment
    }
    return [System.IO.Path]::GetFullPath($canonical)
}

function Test-IsSameOrDescendant {
    param([string]$Candidate, [string]$Parent)

    $candidatePath = $Candidate.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $parentPath = $Parent.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    if ($candidatePath.Equals(
        $parentPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        return $true
    }
    $prefix = $parentPath + [System.IO.Path]::DirectorySeparatorChar
    return $candidatePath.StartsWith(
        $prefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-SeparateTrees {
    param(
        [string]$First,
        [string]$FirstLabel,
        [string]$Second,
        [string]$SecondLabel
    )

    if (
        (Test-IsSameOrDescendant -Candidate $First -Parent $Second) -or
        (Test-IsSameOrDescendant -Candidate $Second -Parent $First)
    ) {
        throw "$FirstLabel and $SecondLabel must not overlap."
    }
}

function Assert-FileOutsideTree {
    param([string]$File, [string]$FileLabel, [string]$Tree, [string]$TreeLabel)

    if (Test-IsSameOrDescendant -Candidate $File -Parent $Tree) {
        throw "$FileLabel must not be inside $TreeLabel."
    }
}

function Read-StrictUtf8 {
    param([string]$Path, [string]$Label)

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if (
        $bytes.Length -ge 3 -and
        $bytes[0] -eq 0xEF -and
        $bytes[1] -eq 0xBB -and
        $bytes[2] -eq 0xBF
    ) {
        throw "$Label must be UTF-8 without a BOM: $Path"
    }
    try {
        return $StrictUtf8.GetString($bytes)
    }
    catch {
        throw "$Label is not valid UTF-8: $Path"
    }
}

function Assert-StrictUtf8Skill {
    param([string]$SkillRoot)

    $rootItem = Get-Item -LiteralPath $SkillRoot
    if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "The source Skill directory must not be a reparse point."
    }
    foreach ($item in Get-ChildItem -LiteralPath $SkillRoot -Recurse -Force) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "The source Skill must not contain reparse points: $($item.FullName)"
        }
        if (-not $item.PSIsContainer) {
            [void](Read-StrictUtf8 -Path $item.FullName -Label "Source Skill file")
        }
    }
}

function Get-NormalizedLf {
    param([string]$Text)

    return $Text.Replace("`r`n", "`n").Replace("`r", "`n")
}

function Get-MarkerState {
    param([string]$Text)

    $beginMatches = [regex]::Matches($Text, [regex]::Escape($BeginMarker))
    $endMatches = [regex]::Matches($Text, [regex]::Escape($EndMarker))
    if ($beginMatches.Count -eq 0 -and $endMatches.Count -eq 0) {
        return [pscustomobject]@{
            HasBlock = $false
            Begin = -1
            EndExclusive = -1
        }
    }
    if ($beginMatches.Count -ne 1 -or $endMatches.Count -ne 1) {
        throw "Codex config contains duplicate, nested, or unmatched AGC markers."
    }
    $begin = $beginMatches[0].Index
    $endExclusive = $endMatches[0].Index + $endMatches[0].Length
    $beginIsWholeLine = (
        ($begin -eq 0 -or $Text[$begin - 1] -eq "`n") -and
        ($endExclusive -le $Text.Length) -and
        (
            $begin + $beginMatches[0].Length -eq $Text.Length -or
            $Text[$begin + $beginMatches[0].Length] -eq "`n"
        )
    )
    $endIsWholeLine = (
        ($endMatches[0].Index -eq 0 -or $Text[$endMatches[0].Index - 1] -eq "`n") -and
        (
            $endExclusive -eq $Text.Length -or
            $Text[$endExclusive] -eq "`n"
        )
    )
    if (-not $beginIsWholeLine -or -not $endIsWholeLine) {
        throw "Codex config AGC markers must be complete lines."
    }
    if ($begin -ge $endMatches[0].Index) {
        throw "Codex config contains reversed AGC markers."
    }
    return [pscustomobject]@{
        HasBlock = $true
        Begin = $begin
        EndExclusive = $endExclusive
    }
}

function ConvertTo-TomlBasicString {
    param([string]$Value)

    return $Value.Replace("\", "\\").Replace('"', '\"')
}

function New-CodexBlock {
    param([string]$Executable, [string]$Memory)

    $escapedExecutable = ConvertTo-TomlBasicString -Value $Executable
    $escapedMemory = ConvertTo-TomlBasicString -Value $Memory
    return @(
        $BeginMarker
        "[mcp_servers.agent_global_context]"
        "enabled = true"
        "command = `"$escapedExecutable`""
        "args = []"
        ""
        "[mcp_servers.agent_global_context.env]"
        "AGC_MEMORY_ROOT = `"$escapedMemory`""
        $EndMarker
    ) -join "`n"
}

function Update-CodexConfig {
    param([string]$Text, [object]$MarkerState, [string]$Block)

    if ($MarkerState.HasBlock) {
        $prefix = $Text.Substring(0, $MarkerState.Begin)
        $suffix = $Text.Substring($MarkerState.EndExclusive)
        return $prefix + $Block + $suffix
    }
    if ($Text.Length -eq 0) {
        return $Block + "`n"
    }
    if ($Text.EndsWith("`n")) {
        return $Text + "`n" + $Block + "`n"
    }
    return $Text + "`n`n" + $Block + "`n"
}

function Test-BytesEqual {
    param([byte[]]$First, [byte[]]$Second)

    if ($First.Length -ne $Second.Length) {
        return $false
    }
    for ($index = 0; $index -lt $First.Length; $index++) {
        if ($First[$index] -ne $Second[$index]) {
            return $false
        }
    }
    return $true
}

function Get-RelativeEntries {
    param([string]$Root)

    $entries = New-Object System.Collections.Generic.List[string]
    foreach (
        $item in Get-ChildItem -LiteralPath $Root -Recurse -Force |
            Sort-Object FullName
    ) {
        $relative = $item.FullName.Substring($Root.Length).TrimStart("\", "/")
        $kind = if ($item.PSIsContainer) { "D" } else { "F" }
        [void]$entries.Add("$kind`:$relative")
    }
    return $entries.ToArray()
}

function Test-DirectoriesEqual {
    param([string]$First, [string]$Second)

    if (-not (Test-Path -LiteralPath $Second -PathType Container)) {
        return $false
    }
    $firstEntries = @(Get-RelativeEntries -Root $First)
    $secondEntries = @(Get-RelativeEntries -Root $Second)
    if ($firstEntries.Count -ne $secondEntries.Count) {
        return $false
    }
    for ($index = 0; $index -lt $firstEntries.Count; $index++) {
        if ($firstEntries[$index] -cne $secondEntries[$index]) {
            return $false
        }
        if ($firstEntries[$index].StartsWith("F:")) {
            $relative = $firstEntries[$index].Substring(2)
            $firstBytes = [System.IO.File]::ReadAllBytes((Join-Path $First $relative))
            $secondBytes = [System.IO.File]::ReadAllBytes((Join-Path $Second $relative))
            if (-not (Test-BytesEqual -First $firstBytes -Second $secondBytes)) {
                return $false
            }
        }
    }
    return $true
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)

    $bytes = $WriteUtf8.GetBytes((Get-NormalizedLf -Text $Text))
    $parent = Split-Path -Parent $Path
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    $temporary = "$Path.agc-$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [System.IO.File]::WriteAllBytes($temporary, $bytes)
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Write-Utf8NoBomIfChanged {
    param([string]$Path, [string]$Text)

    $normalized = Get-NormalizedLf -Text $Text
    $bytes = $WriteUtf8.GetBytes($normalized)
    if (
        (Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Test-BytesEqual -First ([System.IO.File]::ReadAllBytes($Path)) -Second $bytes)
    ) {
        return
    }
    Write-Utf8NoBom -Path $Path -Text $normalized
}

$activeMutationStarted = $false
$backupPath = $null
$skillsToMove = @()
$mutatedSkillNames = @()
$publicNeedsCopy = $false
$configChanged = $false

try {
    # Canonicalize and validate every input before creating any directory.
    $resolvedRepository = Get-ExistingDirectoryPath `
        -Path $RepositoryRoot -Label "RepositoryRoot"
    $resolvedSkills = Get-ExistingDirectoryPath `
        -Path $SkillsRoot -Label "SkillsRoot"
    $resolvedConfig = Get-ExistingFilePath `
        -Path $CodexConfig -Label "CodexConfig"
    $resolvedMemory = Get-AbsolutePath -Path $MemoryRoot -Label "MemoryRoot"
    $resolvedInstall = Get-AbsolutePath -Path $InstallRoot -Label "InstallRoot"
    if (
        (Test-Path -LiteralPath $resolvedMemory) -and
        -not (Test-Path -LiteralPath $resolvedMemory -PathType Container)
    ) {
        throw "MemoryRoot must be a directory path."
    }
    if (
        (Test-Path -LiteralPath $resolvedInstall) -and
        -not (Test-Path -LiteralPath $resolvedInstall -PathType Container)
    ) {
        throw "InstallRoot must be a directory path."
    }

    $sourceSkill = Join-Path $resolvedRepository "skills\$PublicSkillName"
    $sourceSkill = Get-ExistingDirectoryPath `
        -Path $sourceSkill -Label "Repository source Skill"
    $activePublicSkill = Join-Path $resolvedSkills $PublicSkillName

    Assert-SeparateTrees `
        -First $resolvedRepository -FirstLabel "RepositoryRoot" `
        -Second $resolvedSkills -SecondLabel "SkillsRoot"
    Assert-SeparateTrees `
        -First $resolvedRepository -FirstLabel "RepositoryRoot" `
        -Second $resolvedInstall -SecondLabel "InstallRoot"
    Assert-SeparateTrees `
        -First $resolvedSkills -FirstLabel "SkillsRoot" `
        -Second $resolvedInstall -SecondLabel "InstallRoot"
    Assert-SeparateTrees `
        -First $resolvedRepository -FirstLabel "RepositoryRoot" `
        -Second $resolvedMemory -SecondLabel "MemoryRoot"
    Assert-SeparateTrees `
        -First $resolvedSkills -FirstLabel "SkillsRoot" `
        -Second $resolvedMemory -SecondLabel "MemoryRoot"
    Assert-SeparateTrees `
        -First $resolvedInstall -FirstLabel "InstallRoot" `
        -Second $resolvedMemory -SecondLabel "MemoryRoot"
    Assert-FileOutsideTree `
        -File $resolvedConfig -FileLabel "CodexConfig" `
        -Tree $resolvedRepository -TreeLabel "RepositoryRoot"
    Assert-FileOutsideTree `
        -File $resolvedConfig -FileLabel "CodexConfig" `
        -Tree $resolvedSkills -TreeLabel "SkillsRoot"
    Assert-FileOutsideTree `
        -File $resolvedConfig -FileLabel "CodexConfig" `
        -Tree $resolvedInstall -TreeLabel "InstallRoot"
    Assert-FileOutsideTree `
        -File $resolvedConfig -FileLabel "CodexConfig" `
        -Tree $resolvedMemory -TreeLabel "MemoryRoot"

    Assert-StrictUtf8Skill -SkillRoot $sourceSkill
    $originalConfigBytes = [System.IO.File]::ReadAllBytes($resolvedConfig)
    $originalConfigText = Read-StrictUtf8 `
        -Path $resolvedConfig -Label "Codex config"
    $normalizedConfig = Get-NormalizedLf -Text $originalConfigText
    $markerState = Get-MarkerState -Text $normalizedConfig

    $mcpExecutable = [System.IO.Path]::GetFullPath(
        (Join-Path $resolvedInstall "venv\Scripts\agc-mcp.exe")
    )
    $launcher = [System.IO.Path]::GetFullPath(
        (Join-Path $resolvedInstall "bin\agc-mcp.cmd")
    )
    $codexBlock = New-CodexBlock `
        -Executable $mcpExecutable -Memory $resolvedMemory
    $updatedConfig = Update-CodexConfig `
        -Text $normalizedConfig -MarkerState $markerState -Block $codexBlock
    $updatedConfigBytes = $WriteUtf8.GetBytes($updatedConfig)
    $configChanged = -not (
        Test-BytesEqual -First $originalConfigBytes -Second $updatedConfigBytes
    )

    foreach ($name in $RetiredSkillNames) {
        if (Test-Path -LiteralPath (Join-Path $resolvedSkills $name)) {
            $skillsToMove += $name
        }
    }
    $publicNeedsCopy = -not (
        Test-DirectoriesEqual -First $sourceSkill -Second $activePublicSkill
    )
    if ($publicNeedsCopy -and (Test-Path -LiteralPath $activePublicSkill)) {
        $skillsToMove += $PublicSkillName
    }

    # Runtime writes are isolated under InstallRoot and finish before active mutation.
    [System.IO.Directory]::CreateDirectory($resolvedInstall) | Out-Null
    if (-not $SkipRuntimeInstall) {
        $venvPython = Join-Path $resolvedInstall "venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            $pythonCommand = Get-Command python -ErrorAction Stop
            $venvOutput = @(
                & $pythonCommand.Source -m venv (
                    Join-Path $resolvedInstall "venv"
                ) 2>&1
            )
            $venvExitCode = $LASTEXITCODE
            foreach ($line in $venvOutput) {
                [Console]::Error.WriteLine([string]$line)
            }
            if ($venvExitCode -ne 0) {
                throw "Creating the dedicated Runtime virtual environment failed."
            }
        }
        $installOutput = @(
            & $venvPython -m pip install "$resolvedRepository[mcp]" 2>&1
        )
        $installExitCode = $LASTEXITCODE
        foreach ($line in $installOutput) {
            [Console]::Error.WriteLine([string]$line)
        }
        if ($installExitCode -ne 0) {
            throw "Installing the AGC Runtime MCP adapter failed."
        }
        if (-not (Test-Path -LiteralPath $mcpExecutable -PathType Leaf)) {
            throw "The installed AGC MCP executable was not found."
        }
    }
    Write-Utf8NoBomIfChanged `
        -Path $launcher -Text "@`"$mcpExecutable`" %*`n"

    $activeMutationNeeded = (
        $configChanged -or
        $publicNeedsCopy -or
        $skillsToMove.Count -gt 0
    )
    if ($activeMutationNeeded) {
        $backupName = (
            (Get-Date).ToString("yyyyMMdd-HHmmss-fff") +
            "-" +
            [guid]::NewGuid().ToString("N")
        )
        $backupPath = Join-Path $resolvedInstall "backups\$backupName"
        [System.IO.Directory]::CreateDirectory($backupPath) | Out-Null

        $configBackupDirectory = Join-Path $backupPath "codex-config"
        [System.IO.Directory]::CreateDirectory($configBackupDirectory) | Out-Null
        [System.IO.File]::Copy(
            $resolvedConfig,
            (Join-Path $configBackupDirectory (
                [System.IO.Path]::GetFileName($resolvedConfig)
            )),
            $false
        )
        if ($skillsToMove.Count -gt 0) {
            [System.IO.Directory]::CreateDirectory(
                (Join-Path $backupPath "skills")
            ) | Out-Null
        }

        $activeMutationStarted = $true
        foreach ($name in $skillsToMove) {
            $activeSkill = Join-Path $resolvedSkills $name
            $skillBackup = Join-Path $backupPath "skills\$name"
            Copy-Item `
                -LiteralPath $activeSkill `
                -Destination $skillBackup `
                -Recurse
            if (-not (
                Test-DirectoriesEqual -First $activeSkill -Second $skillBackup
            )) {
                throw "Skill backup verification failed: $name"
            }
            $mutatedSkillNames += $name
            Remove-Item -LiteralPath $activeSkill -Recurse -Force
        }
        if ($publicNeedsCopy) {
            Copy-Item `
                -LiteralPath $sourceSkill `
                -Destination $activePublicSkill `
                -Recurse
        }
        if ($configChanged) {
            Write-Utf8NoBom -Path $resolvedConfig -Text $updatedConfig
        }

        # Test-only boundary exercises the same caught-failure rollback path.
        if ($env:AGC_INSTALL_TEST_FAIL_AFTER -eq "config") {
            throw "Injected failure after active config mutation."
        }
    }

    $result = [ordered]@{
        repository_root = $resolvedRepository
        skills_root = $resolvedSkills
        codex_config = $resolvedConfig
        memory_root = $resolvedMemory
        install_root = $resolvedInstall
        mcp_executable = $mcpExecutable
        launcher = $launcher
        backup_path = $backupPath
        restart_required = $true
    }
    [Console]::Out.WriteLine(($result | ConvertTo-Json -Compress))
}
catch {
    if ($activeMutationStarted -and $null -ne $backupPath) {
        try {
            if ($configChanged) {
                $configBackup = Join-Path $backupPath (
                    "codex-config\" +
                    [System.IO.Path]::GetFileName($resolvedConfig)
                )
                if (Test-Path -LiteralPath $configBackup -PathType Leaf) {
                    [System.IO.File]::Copy($configBackup, $resolvedConfig, $true)
                }
            }

            if ($publicNeedsCopy -and (Test-Path -LiteralPath $activePublicSkill)) {
                Remove-Item -LiteralPath $activePublicSkill -Recurse -Force
            }
            foreach ($name in $mutatedSkillNames) {
                $skillBackup = Join-Path $backupPath "skills\$name"
                if (Test-Path -LiteralPath $skillBackup -PathType Container) {
                    $activeSkill = Join-Path $resolvedSkills $name
                    if (Test-Path -LiteralPath $activeSkill) {
                        Remove-Item -LiteralPath $activeSkill -Recurse -Force
                    }
                    Copy-Item `
                        -LiteralPath $skillBackup `
                        -Destination $activeSkill `
                        -Recurse
                }
            }
        }
        catch {
            [Console]::Error.WriteLine(
                "AGC installer rollback failed; inspect the retained backup at $backupPath."
            )
        }
    }
    [Console]::Error.WriteLine("AGC installer failed: $($_.Exception.Message)")
    exit 1
}
