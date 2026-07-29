# Install

AGC Runtime Core is an independent deterministic Python runtime. MCP is an
optional Host Adapter that lets Codex expose the Runtime through one server and
exactly three tools:

```text
agc.read
agc.write
agc.admin
```

The local installer creates a dedicated Runtime virtual environment, installs
one public `agent-global-context` Skill, retires the four alpha companion Skill
directories, and inserts or replaces one marked Codex MCP registration block.
It is safe to rerun.

## Prerequisites

- Windows PowerShell 5.1 or PowerShell 7
- Python 3.10 or newer
- an existing repository checkout
- an existing active Skills directory
- an existing Codex `config.toml`
- distinct repository, Skills, config, Runtime install, and memory paths

`MemoryRoot` and `InstallRoot` may be new directories. Other inputs must
already exist. The installer rejects dangerous overlapping paths before it
changes active files.

## Install for Codex

Use explicit paths so the intended active installation and parallel v2 memory
root are reviewable before execution:

```powershell
$repository = (Resolve-Path "D:\src\agent-global-context").Path
$skills = "$env:USERPROFILE\.agents\skills"
$codexConfig = "$env:USERPROFILE\.codex\config.toml"
$memoryV2 = "$env:USERPROFILE\.agent-global-context-v2"
$runtimeInstall = "$env:USERPROFILE\.agent-global-context-runtime"

& "$repository\scripts\install-local.ps1" `
  -RepositoryRoot $repository `
  -SkillsRoot $skills `
  -CodexConfig $codexConfig `
  -MemoryRoot $memoryV2 `
  -InstallRoot $runtimeInstall
```

The installer:

1. validates paths, the source Skill encoding, and Codex block markers;
2. installs the repository's `mcp` extra into an inactive content-addressed
   virtual environment under
   `<InstallRoot>\venvs\<runtime-content-sha256>`;
3. writes `<InstallRoot>\bin\agc-mcp.cmd`;
4. backs up every active AGC Skill directory that it replaces and the Codex
   config when it changes;
5. leaves only the public `agent-global-context` Skill active; and
6. registers the absolute MCP executable and `AGC_MEMORY_ROOT` in exactly one
   marked Codex block.

Backups are retained under
`<InstallRoot>\backups\<timestamp-and-unique-suffix>\`. A no-op rerun creates
no backup. A caught failure after active mutation begins restores the active
config, launcher, and Skills from the current backup. Runtime upgrades never
modify or remove the previously configured venv; Codex switches to the validated
content-addressed venv only after its final-path Python imports and
`agc-mcp.exe --version` probe pass.

## After Registration

Restart Codex and start a new task so the new Skill and MCP server are loaded.
The server exposes exactly `agc.read`, `agc.write`, and `agc.admin`.

The installer only installs and registers the adapter. It does not initialize
or migrate memory, and it does not enable Codex task capture or backfill.

For a v1-to-v2 rollout, keep the existing v1 root read-only as rollback
material and use a parallel root such as
`~/.agent-global-context-v2`. Retire v1 only through a later explicit,
verified action.

## Test-Only Runtime Skip

`-SkipRuntimeInstall` skips virtual-environment creation and package
installation. It exists for isolated installer integration tests; the
installer still writes the launcher and registration paths. Do not use it for
a normal local deployment unless the expected MCP executable was installed
separately.
