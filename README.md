# Agent Global Context

Markdown-first global context skills for AI agents.

Agent Global Context helps coding agents preserve key user identity, technical preferences, coding habits, work environment, and project knowledge across sessions. It is not a full conversation archive. It is a selective, auditable context layer for information that should influence future agent behavior.

## Why

Long agent sessions eventually lose detail through context limits and compression. The usual workaround is to summarize everything, but full summaries become noisy and hard to trust.

This project takes a different approach:

- Store only high-value context, not complete chat logs.
- Keep memory human-readable, editable, and reviewable in Markdown.
- Recall context by priority and task relevance instead of loading everything.
- Stay agent-neutral: the pattern can be used by Codex, Claude Code, Cursor, OpenCode, and other coding agents that support skills or instruction files.

## Core Model

Agent Global Context uses five priority levels:

- `P0`: user background and identity-level context
- `P1`: technical and collaboration preferences
- `P2`: coding habits and engineering style
- `P3`: project and work-environment knowledge
- `P4`: temporary session state

The goal is not perfect memory. The goal is better continuity.

## Repository Layout

```text
skills/
  agent-global-context/
  agent-global-context-recall/
  agent-global-context-commit/

templates/
  memory/
    config.yaml
    index.md
    user/
    environment/
    projects/
    staging/

docs/
  design.md
  install.md
  examples.md
```

## MVP Skills

- `agent-global-context`: shared schema, directory layout, and policy.
- `agent-global-context-recall`: loads relevant global context before or during work.
- `agent-global-context-commit`: writes confirmed long-term context and session summaries.

Planned later:

- `agent-global-context-capture`: active candidate extraction into staging.
- `agent-global-context-review`: cleanup, deduplication, archival, and correction.

## Default Memory Root

```text
~/.agent-global-context/
```

On Windows:

```text
C:\Users\<user>\.agent-global-context\
```

## Status

This project is in MVP design stage. The initial implementation focuses on a small, portable skill set and Markdown templates.

