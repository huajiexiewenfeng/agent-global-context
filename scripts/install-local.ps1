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

function Assert-NoReparsePointInAncestors {
    param([string]$Path, [string]$Label)

    $current = [System.IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrEmpty($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (
                ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            ) {
                throw "$Label must not use a reparse point: $current"
            }
        }
        $parent = [System.IO.Path]::GetDirectoryName(
            $current.TrimEnd(
                [System.IO.Path]::DirectorySeparatorChar,
                [System.IO.Path]::AltDirectorySeparatorChar
            )
        )
        if (
            [string]::IsNullOrEmpty($parent) -or
            $parent.Equals($current, [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            break
        }
        $current = $parent
    }
}

function Assert-NoReparsePointTree {
    param([string]$Root, [string]$Label)

    $rootItem = Get-Item -LiteralPath $Root -Force
    if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label must not be a reparse point: $Root"
    }
    foreach ($item in Get-ChildItem -LiteralPath $Root -Recurse -Force) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label must not contain reparse points: $($item.FullName)"
        }
    }
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

    Assert-NoReparsePointTree -Root $SkillRoot -Label "The source Skill"
    foreach ($item in Get-ChildItem -LiteralPath $SkillRoot -Recurse -Force) {
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

function Test-IsTomlBareKeyCharacter {
    param([char]$Character)

    $code = [int]$Character
    return (
        ($code -ge [int][char]"A" -and $code -le [int][char]"Z") -or
        ($code -ge [int][char]"a" -and $code -le [int][char]"z") -or
        ($code -ge [int][char]"0" -and $code -le [int][char]"9") -or
        $Character -eq "_" -or
        $Character -eq "-"
    )
}

function Read-TomlTableHeader {
    param([string]$Line)

    $length = $Line.Length
    $index = 0
    while (
        $index -lt $length -and
        ($Line[$index] -eq " " -or $Line[$index] -eq "`t")
    ) {
        $index++
    }
    if ($index -ge $length -or $Line[$index] -ne "[") {
        throw "Malformed TOML table header."
    }
    $index++
    $isArrayTable = $false
    if ($index -lt $length -and $Line[$index] -eq "[") {
        $isArrayTable = $true
        $index++
    }

    $segments = New-Object System.Collections.Generic.List[string]
    while ($true) {
        while (
            $index -lt $length -and
            ($Line[$index] -eq " " -or $Line[$index] -eq "`t")
        ) {
            $index++
        }
        if ($index -ge $length) {
            throw "Malformed TOML table header: missing key."
        }

        $builder = New-Object System.Text.StringBuilder
        if ($Line[$index] -eq '"') {
            $index++
            $closed = $false
            while ($index -lt $length) {
                $character = $Line[$index]
                $index++
                if ($character -eq '"') {
                    $closed = $true
                    break
                }
                if ($character -eq "\") {
                    if ($index -ge $length) {
                        throw "Malformed TOML basic quoted key escape."
                    }
                    $escape = $Line[$index]
                    $index++
                    switch ($escape) {
                        '"' { [void]$builder.Append('"') }
                        "\" { [void]$builder.Append("\") }
                        "b" { [void]$builder.Append([char]8) }
                        "t" { [void]$builder.Append([char]9) }
                        "n" { [void]$builder.Append([char]10) }
                        "f" { [void]$builder.Append([char]12) }
                        "r" { [void]$builder.Append([char]13) }
                        "u" {
                            $digits = 4
                            if ($index + $digits -gt $length) {
                                throw "Malformed TOML Unicode escape."
                            }
                            $hex = $Line.Substring($index, $digits)
                            if ($hex -cnotmatch "^[0-9A-Fa-f]{4}$") {
                                throw "Malformed TOML Unicode escape."
                            }
                            $codePoint = [Convert]::ToInt32($hex, 16)
                            if ($codePoint -ge 0xD800 -and $codePoint -le 0xDFFF) {
                                throw "TOML Unicode escape is not a scalar value."
                            }
                            [void]$builder.Append(
                                [char]::ConvertFromUtf32($codePoint)
                            )
                            $index += $digits
                        }
                        "U" {
                            $digits = 8
                            if ($index + $digits -gt $length) {
                                throw "Malformed TOML Unicode escape."
                            }
                            $hex = $Line.Substring($index, $digits)
                            if ($hex -cnotmatch "^[0-9A-Fa-f]{8}$") {
                                throw "Malformed TOML Unicode escape."
                            }
                            $codePoint = [Convert]::ToInt32($hex, 16)
                            if (
                                $codePoint -gt 0x10FFFF -or
                                ($codePoint -ge 0xD800 -and $codePoint -le 0xDFFF)
                            ) {
                                throw "TOML Unicode escape is not a scalar value."
                            }
                            [void]$builder.Append(
                                [char]::ConvertFromUtf32($codePoint)
                            )
                            $index += $digits
                        }
                        default {
                            throw "Unsupported TOML basic quoted key escape."
                        }
                    }
                    continue
                }
                $code = [int]$character
                if ($code -le 0x1F -or $code -eq 0x7F) {
                    throw "Control character in TOML basic quoted key."
                }
                [void]$builder.Append($character)
            }
            if (-not $closed) {
                throw "Malformed TOML basic quoted key."
            }
        }
        elseif ($Line[$index] -eq "'") {
            $index++
            $closed = $false
            while ($index -lt $length) {
                $character = $Line[$index]
                $index++
                if ($character -eq "'") {
                    $closed = $true
                    break
                }
                $code = [int]$character
                if ($code -le 0x1F -or $code -eq 0x7F) {
                    throw "Control character in TOML literal quoted key."
                }
                [void]$builder.Append($character)
            }
            if (-not $closed) {
                throw "Malformed TOML literal quoted key."
            }
        }
        else {
            if (-not (Test-IsTomlBareKeyCharacter -Character $Line[$index])) {
                throw "Malformed TOML bare table key."
            }
            while (
                $index -lt $length -and
                (Test-IsTomlBareKeyCharacter -Character $Line[$index])
            ) {
                [void]$builder.Append($Line[$index])
                $index++
            }
        }
        [void]$segments.Add($builder.ToString())

        while (
            $index -lt $length -and
            ($Line[$index] -eq " " -or $Line[$index] -eq "`t")
        ) {
            $index++
        }
        if ($index -ge $length) {
            throw "Malformed TOML table header: missing closing bracket."
        }
        if ($Line[$index] -eq ".") {
            $index++
            continue
        }
        if ($isArrayTable) {
            if (
                $Line[$index] -ne "]" -or
                $index + 1 -ge $length -or
                $Line[$index + 1] -ne "]"
            ) {
                throw "Malformed TOML array table closing brackets."
            }
            $index += 2
        }
        else {
            if ($Line[$index] -ne "]") {
                throw "Malformed TOML table closing bracket."
            }
            $index++
        }
        break
    }

    while (
        $index -lt $length -and
        ($Line[$index] -eq " " -or $Line[$index] -eq "`t")
    ) {
        $index++
    }
    if ($index -lt $length -and $Line[$index] -ne "#") {
        throw "Unexpected text after TOML table header."
    }
    return $segments.ToArray()
}

function Assert-NoUnmanagedAgcTable {
    param([string]$Text, [object]$MarkerState)

    $outside = $Text
    if ($MarkerState.HasBlock) {
        $outside = (
            $Text.Substring(0, $MarkerState.Begin) +
            $Text.Substring($MarkerState.EndExclusive)
        )
    }
    $stringMode = "none"
    $arrayDepth = 0
    $inlineTableDepth = 0
    foreach ($line in $outside.Split([char]"`n")) {
        $candidate = $line.TrimStart()
        if (
            $stringMode -eq "none" -and
            $arrayDepth -eq 0 -and
            $inlineTableDepth -eq 0 -and
            $candidate.StartsWith("[")
        ) {
            $segments = @(Read-TomlTableHeader -Line $candidate)
            if (
                $segments.Count -ge 2 -and
                [string]::Equals(
                    $segments[0],
                    "mcp_servers",
                    [System.StringComparison]::Ordinal
                ) -and
                [string]::Equals(
                    $segments[1],
                    "agent_global_context",
                    [System.StringComparison]::Ordinal
                )
            ) {
                throw "Codex config contains an unmanaged agent_global_context MCP table."
            }
            continue
        }

        $index = 0
        while ($index -lt $line.Length) {
            if ($stringMode -eq "multiline-basic") {
                if ($line[$index] -eq "\") {
                    $index += 2
                    continue
                }
                if ($line[$index] -eq '"') {
                    $quoteRun = 0
                    while (
                        $index + $quoteRun -lt $line.Length -and
                        $line[$index + $quoteRun] -eq '"'
                    ) {
                        $quoteRun++
                    }
                }
                else {
                    $quoteRun = 0
                }
                if ($quoteRun -ge 3 -and $quoteRun -le 5) {
                    $stringMode = "none"
                    $index += $quoteRun
                    continue
                }
                if ($quoteRun -gt 5) {
                    $stringMode = "none"
                    $index += 3
                    continue
                }
                $index++
                continue
            }
            if ($stringMode -eq "multiline-literal") {
                if ($line[$index] -eq "'") {
                    $quoteRun = 0
                    while (
                        $index + $quoteRun -lt $line.Length -and
                        $line[$index + $quoteRun] -eq "'"
                    ) {
                        $quoteRun++
                    }
                }
                else {
                    $quoteRun = 0
                }
                if ($quoteRun -ge 3 -and $quoteRun -le 5) {
                    $stringMode = "none"
                    $index += $quoteRun
                    continue
                }
                if ($quoteRun -gt 5) {
                    $stringMode = "none"
                    $index += 3
                    continue
                }
                $index++
                continue
            }
            if ($stringMode -eq "basic") {
                if ($line[$index] -eq "\") {
                    $index += 2
                    continue
                }
                if ($line[$index] -eq '"') {
                    $stringMode = "none"
                }
                $index++
                continue
            }
            if ($stringMode -eq "literal") {
                if ($line[$index] -eq "'") {
                    $stringMode = "none"
                }
                $index++
                continue
            }

            if ($line[$index] -eq "#") {
                break
            }
            if (
                $index + 3 -le $line.Length -and
                $line.Substring($index, 3) -eq '"""'
            ) {
                $stringMode = "multiline-basic"
                $index += 3
                continue
            }
            if (
                $index + 3 -le $line.Length -and
                $line.Substring($index, 3) -eq "'''"
            ) {
                $stringMode = "multiline-literal"
                $index += 3
                continue
            }
            if ($line[$index] -eq '"') {
                $stringMode = "basic"
                $index++
                continue
            }
            if ($line[$index] -eq "'") {
                $stringMode = "literal"
                $index++
                continue
            }
            if ($line[$index] -eq "[") {
                $arrayDepth++
                $index++
                continue
            }
            if ($line[$index] -eq "]") {
                if ($arrayDepth -eq 0) {
                    throw "Unexpected TOML array closing bracket."
                }
                $arrayDepth--
                $index++
                continue
            }
            if ($line[$index] -eq "{") {
                $inlineTableDepth++
                $index++
                continue
            }
            if ($line[$index] -eq "}") {
                if ($inlineTableDepth -eq 0) {
                    throw "Unexpected TOML inline table closing brace."
                }
                $inlineTableDepth--
                $index++
                continue
            }
            $index++
        }
        if ($stringMode -eq "basic" -or $stringMode -eq "literal") {
            throw "Unterminated TOML quoted string."
        }
    }
    if (
        $stringMode -ne "none" -or
        $arrayDepth -ne 0 -or
        $inlineTableDepth -ne 0
    ) {
        throw "Unterminated TOML multiline string or nested value."
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

function Invoke-NativeCommand {
    param([string]$Executable, [string[]]$Arguments)

    $previousPreference = $ErrorActionPreference
    $captured = @()
    $exitCode = 1
    try {
        $ErrorActionPreference = "Continue"
        $captured = @(& $Executable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    foreach ($line in $captured) {
        [Console]::Error.WriteLine([string]$line)
    }
    return $exitCode
}

function Get-RuntimeDeploymentKey {
    param([string]$Repository)

    $runtimeRoot = Join-Path $Repository "agc_runtime"
    $manifestFiles = @(
        (Join-Path $Repository "pyproject.toml"),
        (Join-Path $Repository "README.md")
    )
    if (-not (Test-Path -LiteralPath $runtimeRoot -PathType Container)) {
        throw "Runtime package directory was not found: $runtimeRoot"
    }
    Assert-NoReparsePointTree -Root $runtimeRoot -Label "Runtime package"
    $manifestFiles += @(
        Get-ChildItem -LiteralPath $runtimeRoot -File -Recurse |
            Sort-Object -Property FullName |
            Select-Object -ExpandProperty FullName
    )

    $records = New-Object System.Collections.Generic.List[string]
    foreach ($file in $manifestFiles) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Runtime deployment input was not found: $file"
        }
        $item = Get-Item -LiteralPath $file -Force
        if (
            ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "Runtime deployment input must not be a reparse point: $file"
        }
        $relative = $item.FullName.Substring($Repository.Length)
        $relative = $relative.TrimStart([char[]]"\/").Replace("\", "/")
        $fileHash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
        $records.Add("$relative`0$($fileHash.ToLowerInvariant())")
    }

    $payload = $WriteUtf8.GetBytes(($records -join "`n"))
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($payload)
    }
    finally {
        $sha256.Dispose()
    }
    return (($digest | ForEach-Object { $_.ToString("x2") }) -join "")
}

$activeMutationStarted = $false
$backupPath = $null
$skillsToMove = @()
$mutatedSkillNames = @()
$publicNeedsCopy = $false
$configChanged = $false
$launcherChanged = $false
$launcherExisted = $false
$captureLauncherChanged = $false
$captureLauncherExisted = $false
$captureHookLauncherChanged = $false
$captureHookLauncherExisted = $false
$pendingRuntimePath = $null

try {
    # Reject path aliases before resolving or creating any input path.
    Assert-NoReparsePointInAncestors `
        -Path $RepositoryRoot -Label "RepositoryRoot"
    Assert-NoReparsePointInAncestors -Path $SkillsRoot -Label "SkillsRoot"
    Assert-NoReparsePointInAncestors -Path $CodexConfig -Label "CodexConfig"
    Assert-NoReparsePointInAncestors -Path $MemoryRoot -Label "MemoryRoot"
    Assert-NoReparsePointInAncestors -Path $InstallRoot -Label "InstallRoot"

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
    foreach ($name in @($PublicSkillName) + $RetiredSkillNames) {
        $activeAgcSkill = Join-Path $resolvedSkills $name
        if (Test-Path -LiteralPath $activeAgcSkill) {
            if (-not (Test-Path -LiteralPath $activeAgcSkill -PathType Container)) {
                throw "Active AGC Skill must be a directory: $activeAgcSkill"
            }
            Assert-NoReparsePointTree `
                -Root $activeAgcSkill -Label "Active AGC Skill $name"
        }
    }

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
    Assert-NoUnmanagedAgcTable `
        -Text $normalizedConfig -MarkerState $markerState

    $launcher = [System.IO.Path]::GetFullPath(
        (Join-Path $resolvedInstall "bin\agc-mcp.cmd")
    )
    $captureLauncher = [System.IO.Path]::GetFullPath(
        (Join-Path $resolvedInstall "bin\agc-capture.cmd")
    )
    $captureHookLauncher = [System.IO.Path]::GetFullPath(
        (Join-Path $resolvedInstall "bin\agc-capture-hook.cmd")
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

    if (-not [string]::IsNullOrEmpty($env:AGC_INSTALL_TEST_NATIVE_PROBE)) {
        $probeExitCode = Invoke-NativeCommand `
            -Executable $env:AGC_INSTALL_TEST_NATIVE_PROBE -Arguments @()
        if ($probeExitCode -ne 0) {
            throw "The native-command probe failed with exit code $probeExitCode."
        }
    }

    # Runtime installation is published into a content-addressed directory. The
    # previously configured venv is never mutated or removed.
    [System.IO.Directory]::CreateDirectory($resolvedInstall) | Out-Null
    if ($SkipRuntimeInstall) {
        $mcpExecutable = [System.IO.Path]::GetFullPath(
            (Join-Path $resolvedInstall "venv\Scripts\agc-mcp.exe")
        )
        $captureExecutable = [System.IO.Path]::GetFullPath(
            (Join-Path $resolvedInstall "venv\Scripts\agc-capture.exe")
        )
        $captureHookExecutable = [System.IO.Path]::GetFullPath(
            (Join-Path $resolvedInstall "venv\Scripts\agc-capture-hook.exe")
        )
    }
    else {
        $deploymentKey = Get-RuntimeDeploymentKey -Repository $resolvedRepository
        $venvsRoot = Join-Path $resolvedInstall "venvs"
        $publishedVenv = Join-Path $venvsRoot $deploymentKey
        $venvPython = Join-Path $publishedVenv "Scripts\python.exe"
        $mcpExecutable = Join-Path $publishedVenv "Scripts\agc-mcp.exe"
        $captureExecutable = Join-Path $publishedVenv "Scripts\agc-capture.exe"
        $captureHookExecutable = Join-Path $publishedVenv "Scripts\agc-capture-hook.exe"
        $deploymentMarker = Join-Path $publishedVenv ".agc-deployment-key"

        if (Test-Path -LiteralPath $publishedVenv) {
            if (-not (Test-Path -LiteralPath $publishedVenv -PathType Container)) {
                throw "Runtime deployment path is not a directory: $publishedVenv"
            }
            Assert-NoReparsePointTree `
                -Root $publishedVenv -Label "Published Runtime deployment"
            if (
                -not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or
                -not (Test-Path -LiteralPath $mcpExecutable -PathType Leaf) -or
                -not (Test-Path -LiteralPath $captureExecutable -PathType Leaf) -or
                -not (Test-Path -LiteralPath $captureHookExecutable -PathType Leaf) -or
                -not (Test-Path -LiteralPath $deploymentMarker -PathType Leaf) -or
                (Read-StrictUtf8 -Path $deploymentMarker -Label "Runtime marker").Trim() `
                    -ne $deploymentKey
            ) {
                throw "Existing Runtime deployment is incomplete: $publishedVenv"
            }
        }
        else {
            [System.IO.Directory]::CreateDirectory($venvsRoot) | Out-Null
            $pendingRuntimePath = $publishedVenv

            if (
                -not [string]::IsNullOrEmpty(
                    $env:AGC_INSTALL_TEST_PYTHON
                )
            ) {
                $pythonExecutable = Get-ExistingFilePath `
                    -Path $env:AGC_INSTALL_TEST_PYTHON `
                    -Label "Test Python executable"
            }
            else {
                $pythonCommand = Get-Command python -ErrorAction Stop
                $pythonExecutable = $pythonCommand.Source
            }
            $venvExitCode = Invoke-NativeCommand `
                -Executable $pythonExecutable `
                -Arguments @(
                    "-m",
                    "venv",
                    $publishedVenv
                )
            if ($venvExitCode -ne 0) {
                throw "Creating the dedicated Runtime virtual environment failed."
            }

            $pipArguments = @(
                "-m",
                "pip",
                "install",
                "$resolvedRepository[mcp]"
            )
            if (
                -not [string]::IsNullOrEmpty(
                    $env:AGC_INSTALL_TEST_PIP_NO_DEPS
                )
            ) {
                $pipArguments += "--no-deps"
            }
            $installExitCode = Invoke-NativeCommand `
                -Executable $venvPython -Arguments $pipArguments
            if ($installExitCode -ne 0) {
                throw "Installing the AGC Runtime MCP adapter failed."
            }

            if (-not (Test-Path -LiteralPath $mcpExecutable -PathType Leaf)) {
                throw "The inactive AGC MCP executable was not found."
            }
            if (
                -not (Test-Path -LiteralPath $captureExecutable -PathType Leaf) -or
                -not (Test-Path -LiteralPath $captureHookExecutable -PathType Leaf)
            ) {
                throw "The inactive AGC Capture executables were not found."
            }
            $validationImports = (
                "import agc_runtime; from pathlib import Path; " +
                "p=Path(agc_runtime.__file__).parent; " +
                "assert (p/'default_config.yaml').is_file(); " +
                "assert (p/'schemas'/'capture-extractor-v1.schema.json').is_file()"
            )
            if ([string]::IsNullOrEmpty($env:AGC_INSTALL_TEST_PIP_NO_DEPS)) {
                $validationImports += "; import mcp"
            }
            $validationExitCode = Invoke-NativeCommand `
                -Executable $venvPython `
                -Arguments @("-c", $validationImports)
            if ($validationExitCode -ne 0) {
                throw "The inactive AGC Runtime failed import validation."
            }
            $entryPointExitCode = Invoke-NativeCommand `
                -Executable $mcpExecutable -Arguments @("--version")
            if ($entryPointExitCode -ne 0) {
                throw "The final-path AGC MCP executable failed validation."
            }
            Write-Utf8NoBom `
                -Path (Join-Path $publishedVenv ".agc-deployment-key") `
                -Text "$deploymentKey`n"

            if ($env:AGC_INSTALL_TEST_FAIL_AFTER -eq "runtime-stage") {
                throw "Injected failure after inactive Runtime validation."
            }
        }
    }

    $mcpExecutable = [System.IO.Path]::GetFullPath($mcpExecutable)
    $captureExecutable = [System.IO.Path]::GetFullPath($captureExecutable)
    $captureHookExecutable = [System.IO.Path]::GetFullPath($captureHookExecutable)
    $codexBlock = New-CodexBlock `
        -Executable $mcpExecutable -Memory $resolvedMemory
    $updatedConfig = Update-CodexConfig `
        -Text $normalizedConfig -MarkerState $markerState -Block $codexBlock
    $updatedConfigBytes = $WriteUtf8.GetBytes($updatedConfig)
    $configChanged = -not (
        Test-BytesEqual -First $originalConfigBytes -Second $updatedConfigBytes
    )

    $batchExecutable = $mcpExecutable.Replace("%", "%%")
    $launcherText = "@`"$batchExecutable`" %*`n"
    $launcherBytes = $WriteUtf8.GetBytes((Get-NormalizedLf -Text $launcherText))
    $launcherExisted = Test-Path -LiteralPath $launcher -PathType Leaf
    $launcherChanged = -not (
        $launcherExisted -and
        (Test-BytesEqual `
            -First ([System.IO.File]::ReadAllBytes($launcher)) `
            -Second $launcherBytes)
    )
    $captureBatchExecutable = $captureExecutable.Replace("%", "%%")
    $captureLauncherText = "@`"$captureBatchExecutable`" %*`n"
    $captureLauncherBytes = $WriteUtf8.GetBytes(
        (Get-NormalizedLf -Text $captureLauncherText)
    )
    $captureLauncherExisted = Test-Path -LiteralPath $captureLauncher -PathType Leaf
    $captureLauncherChanged = -not (
        $captureLauncherExisted -and
        (Test-BytesEqual `
            -First ([System.IO.File]::ReadAllBytes($captureLauncher)) `
            -Second $captureLauncherBytes)
    )
    $captureHookBatchExecutable = $captureHookExecutable.Replace("%", "%%")
    $captureHookLauncherText = "@`"$captureHookBatchExecutable`" %*`n"
    $captureHookLauncherBytes = $WriteUtf8.GetBytes(
        (Get-NormalizedLf -Text $captureHookLauncherText)
    )
    $captureHookLauncherExisted = Test-Path `
        -LiteralPath $captureHookLauncher -PathType Leaf
    $captureHookLauncherChanged = -not (
        $captureHookLauncherExisted -and
        (Test-BytesEqual `
            -First ([System.IO.File]::ReadAllBytes($captureHookLauncher)) `
            -Second $captureHookLauncherBytes)
    )

    $activeMutationNeeded = (
        $configChanged -or
        $launcherChanged -or
        $captureLauncherChanged -or
        $captureHookLauncherChanged -or
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
        if ($launcherExisted) {
            $launcherBackupDirectory = Join-Path $backupPath "bin"
            [System.IO.Directory]::CreateDirectory($launcherBackupDirectory) |
                Out-Null
            [System.IO.File]::Copy(
                $launcher,
                (Join-Path $launcherBackupDirectory "agc-mcp.cmd"),
                $false
            )
        }
        if ($captureLauncherExisted -or $captureHookLauncherExisted) {
            $launcherBackupDirectory = Join-Path $backupPath "bin"
            [System.IO.Directory]::CreateDirectory($launcherBackupDirectory) |
                Out-Null
        }
        if ($captureLauncherExisted) {
            [System.IO.File]::Copy(
                $captureLauncher,
                (Join-Path $launcherBackupDirectory "agc-capture.cmd"),
                $false
            )
        }
        if ($captureHookLauncherExisted) {
            [System.IO.File]::Copy(
                $captureHookLauncher,
                (Join-Path $launcherBackupDirectory "agc-capture-hook.cmd"),
                $false
            )
        }
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
        if ($launcherChanged) {
            Write-Utf8NoBom -Path $launcher -Text $launcherText
        }
        if ($captureLauncherChanged) {
            Write-Utf8NoBom -Path $captureLauncher -Text $captureLauncherText
        }
        if ($captureHookLauncherChanged) {
            Write-Utf8NoBom `
                -Path $captureHookLauncher -Text $captureHookLauncherText
        }

        # Test-only boundary exercises the same caught-failure rollback path.
        if ($env:AGC_INSTALL_TEST_FAIL_AFTER -eq "config") {
            throw "Injected failure after active config mutation."
        }
    }

    $pendingRuntimePath = $null
    $result = [ordered]@{
        repository_root = $resolvedRepository
        skills_root = $resolvedSkills
        codex_config = $resolvedConfig
        memory_root = $resolvedMemory
        install_root = $resolvedInstall
        mcp_executable = $mcpExecutable
        capture_executable = $captureExecutable
        capture_hook_executable = $captureHookExecutable
        launcher = $launcher
        capture_launcher = $captureLauncher
        capture_hook_launcher = $captureHookLauncher
        backup_path = $backupPath
        restart_required = $true
    }
    [Console]::Out.WriteLine(($result | ConvertTo-Json -Compress))
}
catch {
    $rollbackSucceeded = $true
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

            if ($launcherChanged) {
                $launcherBackup = Join-Path $backupPath "bin\agc-mcp.cmd"
                if ($launcherExisted) {
                    if (Test-Path -LiteralPath $launcherBackup -PathType Leaf) {
                        [System.IO.File]::Copy($launcherBackup, $launcher, $true)
                    }
                }
                elseif (Test-Path -LiteralPath $launcher -PathType Leaf) {
                    Remove-Item -LiteralPath $launcher -Force
                }
            }
            if ($captureLauncherChanged) {
                $captureLauncherBackup = Join-Path $backupPath "bin\agc-capture.cmd"
                if ($captureLauncherExisted) {
                    if (Test-Path -LiteralPath $captureLauncherBackup -PathType Leaf) {
                        [System.IO.File]::Copy(
                            $captureLauncherBackup, $captureLauncher, $true
                        )
                    }
                }
                elseif (Test-Path -LiteralPath $captureLauncher -PathType Leaf) {
                    Remove-Item -LiteralPath $captureLauncher -Force
                }
            }
            if ($captureHookLauncherChanged) {
                $captureHookLauncherBackup = Join-Path `
                    $backupPath "bin\agc-capture-hook.cmd"
                if ($captureHookLauncherExisted) {
                    if (
                        Test-Path -LiteralPath $captureHookLauncherBackup `
                            -PathType Leaf
                    ) {
                        [System.IO.File]::Copy(
                            $captureHookLauncherBackup,
                            $captureHookLauncher,
                            $true
                        )
                    }
                }
                elseif (Test-Path -LiteralPath $captureHookLauncher -PathType Leaf) {
                    Remove-Item -LiteralPath $captureHookLauncher -Force
                }
            }
        }
        catch {
            $rollbackSucceeded = $false
            [Console]::Error.WriteLine(
                "AGC installer rollback failed; inspect the retained backup at $backupPath."
            )
        }
    }
    if (
        $rollbackSucceeded -and
        $null -ne $pendingRuntimePath -and
        (Test-Path -LiteralPath $pendingRuntimePath -PathType Container)
    ) {
        try {
            Remove-Item -LiteralPath $pendingRuntimePath -Recurse -Force
        }
        catch {
            [Console]::Error.WriteLine(
                "AGC installer could not remove the inactive failed Runtime at " +
                "$pendingRuntimePath."
            )
        }
    }
    [Console]::Error.WriteLine("AGC installer failed: $($_.Exception.Message)")
    exit 1
}
