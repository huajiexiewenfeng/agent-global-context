# Agent Global Context

English | [简体中文](README.zh.md)

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

## v2 Memory Model

The v2 model separates kind, lifecycle, confidence, temporal behavior, recall metadata, sensitivity, and provenance. Memory is discovered progressively:

```text
overview -> search -> get -> history/evidence
```

No personal Memory Card is injected by default. The LLM decides whether memory is relevant, what to read, and whether to apply it. Recall metadata is guidance, not a forced prompt-injection rule.

Normal and eligible personal memories remain human-readable Markdown. Sensitive persistence is fixed to `disabled` in v2, and secrets are never stored.

## Runtime Foundation

The repository now includes an independent deterministic Python Runtime Foundation. It owns schemas, strict UTF-8 I/O, lifecycle gates, exact source-key idempotency, Markdown storage, sanitized events, progressive reads, hard forget, validation, backup, and restore.

The Runtime does not decide semantic similarity and does not invent `match_memory_id`. Those judgments stay with the LLM.

It exposes three structured host tools:

```text
agc.read
agc.write
agc.admin
```

The local CLI is a host adapter, not a required human workflow:

```text
agc read  --root <path> --input <json-file|->
agc write --root <path> --input <json-file|->
agc admin --root <path> --input <json-file|->
```

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
rerun. The quality-first formalization Runtime release is `0.4.1`; the installer also
publishes stable local `agc-capture.cmd` and `agc-capture-hook.cmd` launchers
beside `agc-mcp.cmd`.

The installer does not migrate memory, enable Codex task capture or backfill,
or automatically promote Capture observations. Its packaged defaults remain `capture.enabled=false` and
`capture.mode=off`; installing the launchers does not register a Hook or a
scheduled task. Keep v1 read-only as rollback material until a later explicit,
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
- [Agent Global Context v2 approved design (Chinese)](docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md)
- [Skill–MCP–Runtime architecture retrospective (Chinese)](docs/skill-mcp-runtime-pattern.md)
- [Install](docs/install.md)
- [Examples](docs/examples.md)
- [Full Flow Example](docs/full-flow-example.md)
- [Capture operations](docs/capture-operations.md)

## Status

The v2 Runtime, single public Skill, three-tool MCP adapter, deterministic
parallel migration support, and repeatable local installer are implemented.
The installer does not enable Codex side-channel capture or backfill.
