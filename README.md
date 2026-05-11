# Agent Global Context

English | [简体中文](README.zh.md)

Markdown-first global context skills for AI agents.

Agent Global Context helps coding agents preserve key user identity, technical preferences, coding habits, work environment, and project knowledge across sessions. It is not a full conversation archive. It is a selective, auditable context layer for information that should influence future agent behavior.

## Why

Long agent sessions eventually lose detail through context limits and compression. The usual workaround is to summarize everything, but full summaries become noisy and hard to trust.

This project takes a different approach:

- Store only high-value context, not complete chat logs.
- Keep context human-readable, editable, and reviewable in Markdown.
- Recall context by priority and task relevance instead of loading everything.
- Keep auto capture safe: candidates go to staging first, not long-term memory.
- Stay agent-neutral: the pattern can be used by Codex, Claude Code, Cursor, OpenCode, and other coding agents that support skills or instruction files.

## Core Model

Agent Global Context uses five priority levels:

- `P0`: user background and identity-level context
- `P1`: technical and collaboration preferences
- `P2`: coding habits and engineering style
- `P3`: project and work-environment knowledge
- `P4`: temporary session state

The goal is not perfect memory. The goal is better continuity.

## Quick Start

1. Copy the skills into your agent skill directory.

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

## Alpha MVP Skills

- `agent-global-context`: shared schema, directory layout, and policy.
- `agent-global-context-recall`: loads relevant global context before or during work.
- `agent-global-context-capture`: observes strong signals and writes candidates to staging only.
- `agent-global-context-review`: reviews, promotes, rejects, expires, and cleans candidates.
- `agent-global-context-commit`: writes confirmed long-term context and session summaries.

Auto capture is enabled by default, but it only writes candidates to staging. Long-term memory still requires review and commit.

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
- [Install](docs/install.md)
- [Examples](docs/examples.md)
- [Full Flow Example](docs/full-flow-example.md)

## Status

This project is in alpha MVP stage.
