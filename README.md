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

Codex side-channel capture and v1 migration are separate rollout plans and are not activated by this foundation.

## Quick Start

1. Install the skills with `npx`.

```bash
npx skills add huajiexiewenfeng/agent-global-context
```

This installs all five skills:

```text
skills/agent-global-context/
skills/agent-global-context-recall/
skills/agent-global-context-commit/
skills/agent-global-context-capture/
skills/agent-global-context-review/
```

2. Create the memory root.

```text
~/.agent-global-context/
```

3. Copy the template memory files.

```text
templates/memory/* -> ~/.agent-global-context/
```

4. Add an agent instruction.

```text
At the start of substantial work, use agent-global-context-recall.
Use agent-global-context-capture for strong durable context signals.
Use agent-global-context-review when candidate review is suggested.
Use agent-global-context-commit when the user asks to remember something or compress a session.
```

5. Try the basic flow.

```text
Load my global context.
Remember that I prefer design discussion before implementation.
Review my pending global context candidates.
Compress this session into global context.
```

## Alpha Skills During the Runtime Phase

- `agent-global-context`: shared schema, directory layout, and policy.
- `agent-global-context-recall`: loads relevant global context before or during work.
- `agent-global-context-capture`: observes strong signals and writes candidates to staging only.
- `agent-global-context-review`: reviews, promotes, rejects, expires, and cleans candidates.
- `agent-global-context-commit`: writes confirmed long-term context and session summaries.

These five skills remain the active compatibility layer while the v2 Recall/Skill Adapter is implemented. Their existing candidate workflow remains unchanged in this phase; the new Runtime does not silently activate Codex capture or migrate v1 data.

## Candidate Flow

```text
auto capture
  -> staging/inbox.md or staging/pending-review.md
  -> review
  -> commit
  -> long-term memory
```

Candidates are not facts. They do not enter default recall unless the user asks to review them or they are directly relevant.

## Repository Layout

```text
skills/
  agent-global-context/
    references/
  agent-global-context-recall/
  agent-global-context-commit/
  agent-global-context-capture/
  agent-global-context-review/

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

## Default Memory Root

```text
~/.agent-global-context/
```

On Windows:

```text
C:\Users\<user>\.agent-global-context\
```

## Documentation

- [Architecture](docs/architecture.md)
- [Design](docs/design.md)
- [Agent Global Context v2 approved design (Chinese)](docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md)
- [Install](docs/install.md)
- [Examples](docs/examples.md)
- [Full Flow Example](docs/full-flow-example.md)

## Status

The v2 Runtime Foundation is implemented in the repository. The five alpha skills remain active during the adapter phase. Codex side-channel capture and v1 migration are designed but not activated.
