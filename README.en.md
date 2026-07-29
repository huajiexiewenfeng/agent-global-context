# Agent Global Context

Markdown-first personal memory for AI agents.

Agent Global Context helps agents remember a real, changing person and support their work, life, learning, and research without turning memory into prompt noise. It is not a full conversation archive. It is a selective, auditable context layer for information that can materially improve future help.

## Why

Long agent sessions eventually lose detail through context limits and compression. The usual workaround is to summarize everything, but full summaries become noisy and hard to trust.

This project takes a different approach:

- Store only high-value context, not complete chat logs.
- Keep context human-readable, editable, and reviewable in Markdown.
- Recall context by priority and task relevance instead of loading everything.
- Keep auto capture safe: candidates go to staging first, not long-term memory.
- Stay agent-neutral: the pattern can be used by Codex, Claude Code, Cursor, OpenCode, and other coding agents that support skills or instruction files.

## North Star

- Remember the person, not just the current project.
- Help the person grow across work, life, learning, and research.
- Use the minimum relevant memory and stay quiet when memory would add noise.

## v2 Runtime Foundation

The repository includes an independent deterministic Python runtime for schemas, strict UTF-8 I/O, lifecycle gates, exact source-key idempotency, Markdown storage, sanitized events, progressive reads, hard forget, validation, backup, and restore.

Memory is discovered progressively:

```text
overview -> search -> get -> history/evidence
```

No personal card is injected by default. The LLM decides relevance, semantic similarity, `disposition`, and `match_memory_id`; the Runtime only provides deterministic data and policy enforcement.

Sensitive persistence is fixed to `disabled` in v2, and secrets are never stored.

The Runtime exposes `agc.read`, `agc.write`, and `agc.admin`. Its CLI is a host adapter rather than a required human workflow.

The Runtime Core is independent. MCP is an optional Host Adapter; installing
the adapter does not enable Codex task capture or backfill.

## Quick Start

1. Choose distinct repository, active Skills, Codex config, Runtime install, and
   memory paths. A parallel v2 memory root such as
   `~/.agent-global-context-v2` is recommended for a v1 upgrade.

2. Run the repeatable local installer with explicit paths.

```powershell
$repository = (Resolve-Path "D:\src\agent-global-context").Path
& "$repository\scripts\install-local.ps1" `
  -RepositoryRoot $repository `
  -SkillsRoot "$env:USERPROFILE\.agents\skills" `
  -CodexConfig "$env:USERPROFILE\.codex\config.toml" `
  -MemoryRoot "$env:USERPROFILE\.agent-global-context-v2" `
  -InstallRoot "$env:USERPROFILE\.agent-global-context-runtime"
```

3. Restart Codex and start a new task.

The installer leaves one public `agent-global-context` Skill and registers
exactly three MCP tools through one server: `agc.read`, `agc.write`, and
`agc.admin`. It keeps unique backups of replaced active files and is safe to
rerun.

The installer does not migrate memory and does not enable Codex task capture
or backfill. Keep v1 read-only as rollback material until a later explicit,
verified retirement.

## Repository Layout

```text
skills/
  agent-global-context/
    references/

templates/
  memory/
    config.yaml
    index.md
    user/
    environment/
    projects/
    staging/

docs/
  architecture.md
  architecture.en.md
  architecture.zh.md
  design.md
  design.en.md
  design.zh.md
  install.md
  examples.md
  full-flow-example.md
```

## Memory Root

```text
~/.agent-global-context-v2/
```

On Windows:

```text
C:\Users\<user>\.agent-global-context-v2\
```

An existing v1 `~/.agent-global-context` root should remain read-only rollback
material until it is explicitly retired.

## Documentation

- [Architecture](docs/architecture.md)
- [Design](docs/design.md)
- [Install](docs/install.md)
- [Examples](docs/examples.md)
- [Full Flow Example](docs/full-flow-example.md)

## Status

The v2 Runtime, single public Skill, three-tool MCP adapter, deterministic
parallel migration support, and repeatable local installer are implemented.
The installer does not enable Codex side-channel capture or backfill.
