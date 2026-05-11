# Agent Global Context Architecture

## Overview

Agent Global Context is a Markdown-first global context layer for AI agents. It is designed to preserve key cross-session context without turning memory into a full transcript archive.

The system is built around three ideas:

1. **Priority-based context**: not all memory has the same value or recall frequency.
2. **Human-auditable storage**: long-term context is stored as Markdown entries with small metadata blocks.
3. **Skill-driven operations**: agents use focused skills to recall, commit, and later review global context.

The architecture is intentionally lightweight. The MVP uses files, folders, and skill instructions only. Databases, vector search, and background daemons are optional future layers.

## Goals

- Preserve durable user, technical, coding, environment, and project context across sessions.
- Help agents continue work without rediscovering stable facts.
- Keep memory readable, editable, and reviewable by humans.
- Avoid context explosion by loading only relevant memory.
- Support multiple agents without naming or depending on a specific agent runtime.

## Non-Goals

- Store every conversation message.
- Replace the active model context window.
- Store secrets, credentials, or private keys.
- Infer and persist sensitive personal judgments without user confirmation.
- Require a database or vector index in the MVP.

## System Components

```text
agent-global-context/
  skills/
    agent-global-context/
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
```

### Core Policy Skill

`agent-global-context` is the shared policy skill.

It defines:

- memory root location
- priority model
- memory item schema
- directory layout
- recall rules
- write rules
- sensitive memory rules

It is used when designing, configuring, auditing, or modifying the global context system.

### Recall Skill

`agent-global-context-recall` is responsible for reading memory.

It answers:

- Which memory files should be loaded for this task?
- Should the agent load only summaries or full entries?
- Is this a project task, code task, environment task, or continuation task?

Recall is intentionally selective. It begins from `index.md`, then follows priority and relevance rules.

### Commit Skill

`agent-global-context-commit` is responsible for writing memory.

It handles:

- explicit "remember this" requests
- session compression
- durable preference updates
- project decision recording
- active task state updates

Commit is conservative. Every long-term memory item should include metadata. `P0-P2` items require a rationale; `P3-P4` items should include one when it adds useful context.

### Capture Skill

`agent-global-context-capture` implements alpha auto capture.

Auto capture implements the `observe` stage. It identifies signals that may have long-term value and writes candidate entries to `staging/inbox.md`.

Auto capture is enabled by default. It only creates candidates. It does not create long-term memory. Anything that becomes long-term memory must still pass through commit.

### Review Skill

`agent-global-context-review` reviews staged candidates and maintains candidate lifecycle.

It should help:

- deduplicate memory
- archive stale session state
- resolve contradictions
- review pending sensitive memories
- promote useful staged memories
- expire stale candidates

## Memory Root

Default memory root:

```text
~/.agent-global-context/
```

Windows example:

```text
C:\Users\<user>\.agent-global-context\
```

This location is intentionally agent-neutral. The same global context can be read by different AI coding agents if they support compatible skill or instruction workflows.

## Memory Directory Layout

```text
~/.agent-global-context/
  config.yaml
  index.md

  user/
    profile.md
    preferences.md
    coding-style.md

  environment/
    machine.md
    agent.md

  projects/
    <project-id>/
      overview.md
      engineering.md
      decisions.md
      active.md
      sessions/

  staging/
    inbox.md
    pending-review.md
    rejected.md
```

## File Responsibilities

`config.yaml` controls behavior such as auto capture, recall policy, write policy, and sensitive memory rules.

Auto capture is enabled by default. It can be disabled in configuration.

Staging files exist in the template, but they are not part of an automatic MVP flow. They are used only when the user explicitly asks to stage memory or when sensitive/high-impact context should wait for review.

Auto capture configuration uses:

```yaml
auto_capture:
  enabled: true
  categories:
    preferences: true
    corrections: true
    identity: true
    project_decisions: true
  retention_days: 14
  recall_inbox: false
review:
  session_start_notice: true
  prompt_when_pending_count_gte: 5
  prompt_when_oldest_pending_days_gte: 7
```

`index.md` is the recall entry point. It maps projects, lists default recall files, and points to active project state.

`user/profile.md` stores `P0` user background and durable identity-level context.

`user/preferences.md` stores `P1` technical, tooling, architecture, and collaboration preferences.

`user/coding-style.md` stores `P2` coding habits, testing habits, review expectations, and implementation style.

`environment/machine.md` stores `P3` operating system, shell, paths, tools, permissions, and machine-specific facts.

`environment/agent.md` stores `P3` agent setup, skill locations, plugins, and operating constraints.

`projects/<project-id>/overview.md` stores `P3` project purpose, domain, stack, and architecture overview.

`projects/<project-id>/engineering.md` stores `P3` commands, dependencies, directory structure, and known engineering pitfalls.

`projects/<project-id>/decisions.md` stores `P3` durable project decisions and rationale.

`projects/<project-id>/active.md` stores `P4` current task state, next actions, blockers, and recent sessions.

`projects/<project-id>/sessions/` stores dated `P4` session summaries.

`staging/inbox.md` stores candidate memories that may be promoted later.

`staging/pending-review.md` stores sensitive or high-impact candidates that require user confirmation.

`staging/rejected.md` stores rejected memories and anti-memories that should not be re-added.

## Priority Model

| Priority | Meaning | Default Recall |
| --- | --- | --- |
| `P0` | User background and identity-level context | Read summary for substantial work |
| `P1` | Technical and collaboration preferences | Read for planning, architecture, tool choice |
| `P2` | Coding habits and engineering style | Read for coding, review, testing, refactoring |
| `P3` | Project and environment knowledge | Read when cwd or request maps to a project/environment |
| `P4` | Temporary session state | Read only for continuation requests |

This priority model prevents memory from becoming one large undifferentiated context blob.

## Recall Budget

Priority defines importance, relevance defines inclusion, and budget defines depth.

When multiple priority levels match a task, load summaries first:

1. `index.md`
2. `P0` `Recall Summary`
3. active project `P3` summary
4. directly relevant `P1/P2` summaries
5. `P4` active state and recent sessions only for continuation

If context budget is tight, drop old `P4` session details before dropping active project context or directly relevant user preferences.

## Memory Item Schema

Long-term memory uses Markdown entries:

```markdown
## memory-id

- type: preference
- priority: P1
- confidence: confirmed
- source: user_explicit
- scope: global
- status: active
- created_at: YYYY-MM-DD
- updated_at: YYYY-MM-DD

Memory content.

Rationale:
Why this should influence future agent behavior.
```

Required fields:

- `type`
- `priority`
- `confidence`
- `source`
- `scope`
- `status`
- `created_at`
- `updated_at`

The `Rationale` section is required for long-term memory. It forces each memory item to justify its future value.

For practical use, `Rationale` is required for `P0-P2`. It is recommended but optional for `P3-P4` when the value is obvious from project commands, decisions, or task state.

## Confidence Model

Use four confidence values:

- `confirmed`: the user explicitly stated it, approved it, or asked the agent to remember it.
- `observed`: supported by reliable local evidence such as repository files, command output, configuration, or repeated visible behavior.
- `inferred`: derived by the agent from context, but not directly confirmed.
- `tentative`: weak, ambiguous, or likely temporary.

Do not mark agent guesses as `confirmed`.

## Recall Flow

```text
User request
  -> detect whether global context is relevant
  -> read config.yaml
  -> read index.md
  -> load P0 Recall Summary
  -> classify task type
  -> load relevant P1/P2/P3/P4 files
  -> proceed with task using loaded context
```

Task classification:

- planning or technical choice -> load `P1`
- code implementation/review/testing -> load `P1` and `P2`
- environment or command work -> load environment `P3`
- project-specific work -> load matching project `P3`
- "continue", "resume", "last time" -> load project `P4`

Recall should prefer `Recall Summary` sections before full detailed entries.

## Project Resolution

Project-scoped recall and writes need a stable `<project-id>`.

Resolve project ids in this order:

1. Use explicit project bindings confirmed by the user.
2. Match the current working directory or user-provided path against `index.md` `Project Map`.
3. If inside a Git repository, derive a candidate from the Git remote repository slug.
4. If no Git remote is available, derive a candidate from the current directory name.
5. If the project id is new or ambiguous, ask the user before creating or relying on project memory.

Project ids should be lowercase ASCII slugs. Convert spaces and underscores to hyphens, remove unsupported characters, collapse repeated hyphens, and trim leading or trailing hyphens.

User-confirmed bindings are authoritative. Git remote and directory-name slugs are heuristics and can be fragile in monorepos, forks, submodules, or multiple worktrees.

Examples:

```text
C:\Users\me\Documents\New Project 2 -> new-project-2
git@github.com:owner/Agent Global Context.git -> agent-global-context
```

## Commit Flow

```text
User asks to remember or compress
  -> classify priority P0-P4
  -> check sensitive policy
  -> choose destination file
  -> read existing target file
  -> deduplicate or update existing entry
  -> write Markdown memory item
  -> update index.md if recall behavior changed
  -> report changed files
```

Explicit memory requests can usually be committed directly unless the content is sensitive.

Active or inferred candidate memories should be staged first unless configuration allows direct commit and the source is reliable.

## Dedupe and Update Flow

Before appending a memory item, scan the target file for existing entries with the same meaning.

Update an existing entry when the new information:

- clarifies the same fact or preference
- changes confidence or source
- adds rationale or scope
- refreshes `updated_at`

Append a new entry only when it represents a distinct durable fact, preference, habit, decision, or task state.

If new information replaces old information, mark the old entry `status: superseded` and use `supersedes` on the new entry when useful. Do not silently overwrite confirmed memory with inferred memory.

## Auto Capture Flow

```text
Conversation signal
  -> evaluate capture trigger
  -> apply sensitive filtering
  -> write candidate to staging/inbox.md or pending-review.md
  -> wait for review or commit
```

Capture only strong signals:

- user preferences or habits
- durable project or workflow decisions
- user corrections to agent behavior
- stable identity-level context such as background, role, language, or work environment

Do not capture:

- one-off task details
- temporary state
- undecided exploratory ideas
- small talk or unrelated discussion
- unconfirmed psychological, personality, motivation, or emotional-state inferences

Candidate entries should include:

- `source`
- `proposed_priority`
- `proposed_confidence`
- `rationale`
- `created_at`
- `status`

Auto capture confidence is capped at `observed`, defaults to `inferred`, and uses `tentative` for weak evidence. `confirmed` requires explicit user action.

Sensitive filtering applies during observe. Secrets and credentials must not enter staging. Personal sensitive context should go to pending review only if it may be legitimate to remember and the user is asked. Unconfirmed psychological or personality inferences should be dropped by default.

`staging/inbox.md` is not part of default recall. Candidates may be read only when the user asks to review them or when a candidate is highly relevant to the current task. Even then, candidates must not be treated as confirmed long-term facts.

Operating principle:

```text
Auto capture may notice.
Staging may hold.
Review may approve.
Commit may remember.
Recall must not trust unconfirmed candidates.
```

## Candidate Review Flow

```text
staging candidate
  -> review confidence and sensitivity
  -> promote, reject, expire, or keep pending
  -> if promoted, run commit rules
  -> write formal memory item
  -> update candidate status
```

Promotion rules:

- `confirmed`: can be promoted.
- `observed`: can be promoted when source is reliable and non-sensitive.
- `inferred`: requires user confirmation.
- `tentative`: requires confirmation or repeated evidence.

When promoted, a candidate should record:

```markdown
- status: promoted
- reviewed_at: YYYY-MM-DD
- promoted_to: path/to/file.md#memory-id
```

Rejected and expired candidates should also record `reviewed_at` and a short reason.

The agent should suggest review when:

- pending candidate count reaches the configured threshold
- oldest pending candidate age reaches the configured threshold
- sensitive/high-impact candidates exist in `pending-review.md`
- a candidate is directly relevant before a commit

Review prompts should not block normal work unless confirmation or expiration policy requires it.

## Conflict Resolution

Use this precedence order:

1. Current explicit user instruction.
2. Safety and sensitive memory policy.
3. Project-specific `P3` constraints and decisions for the active project.
4. User coding habits `P2`.
5. User technical preferences `P1`.
6. User profile context `P0`.
7. Temporary session state `P4`.

Inside a project, confirmed project conventions override general personal preferences. If this conflict affects the decision, mention it briefly.

## Session Compression Flow

```text
Session end or user request
  -> summarize goal, decisions, current state, next actions
  -> write sessions/YYYY-MM-DD-HHMM.md
  -> update active.md
  -> promote only durable P0-P3 memories
  -> leave noisy details out
```

Session summaries are not full transcripts. They are recovery points for future work.

## Sensitive Memory Gate

Sensitive or high-impact memory must not be silently committed.

Ask before writing:

- real names, contact information, addresses, accounts
- financial, medical, family, or private relationship details
- company secrets or confidential business information
- psychological, personality, motivation, or emotional-state inferences

Never store:

- passwords
- API keys
- private keys
- authentication tokens
- recovery codes

If a user asks to store secrets, the agent should explain that this Markdown memory system is not secret storage.

## Data Lifecycle

```text
observe -> stage -> commit -> review -> archive/supersede/reject
```

MVP supports:

- recall
- explicit commit
- session compression
- candidate-only auto capture
- candidate review and promotion

The alpha MVP does not support automatic long-term memory writes. Candidate promotion still runs through commit rules.

Future lifecycle support:

- scheduled cleanup
- contradiction detection
- memory aging and archival

`P4` active state should be treated as temporary. Update `active.md` in place, remove completed next actions, and avoid carrying stale blockers into unrelated work. Session summaries may remain as historical recovery points, but recall should load only recent summaries referenced by `active.md` or allowed by configuration.

## Agent-Neutral Design

The project avoids agent-specific names in:

- repository name
- memory root path
- skill names
- file names
- docs

This keeps the system portable across coding agents.

Agent-specific details should live in:

```text
environment/agent.md
```

or in host-agent installation docs.

## Extension Points

### Search Layer

Future versions may add:

- ripgrep-based local search
- SQLite full-text search
- vector search
- generated index files

The Markdown files should remain the source of truth.

## Failure Modes

### Memory Pollution

Cause: committing too much or committing weak inferences.

Mitigation:

- require rationale
- use staging
- mark source and confidence
- confirm sensitive or high-impact memory

### Context Explosion

Cause: loading all memory files by default.

Mitigation:

- start from `index.md`
- use priority-based recall
- prefer `Recall Summary`
- limit session history loading

### Stale Memory

Cause: old preferences or project state remain active.

Mitigation:

- use `status`
- support `review_after`
- archive obsolete P4 state
- supersede old decisions explicitly

### Agent-Specific Lock-In

Cause: encoding assumptions for one agent runtime.

Mitigation:

- keep names agent-neutral
- keep storage plain Markdown/YAML
- put runtime details in installation docs

## MVP Boundary

The MVP includes:

- core policy skill
- recall skill
- commit skill
- capture skill
- review skill
- Markdown memory templates
- architecture, install, and example docs

The MVP does not include:

- CLI installer
- database index
- vector search
- background automation

## Success Criteria

The MVP is successful when an agent can:

1. Load relevant user and project context without reading everything.
2. Commit a user preference with metadata and rationale.
3. Compress a session into a project recovery point.
4. Continue recent work from `active.md` and recent session summaries.
5. Avoid storing sensitive or low-value information by default.
6. Resolve project context predictably.
7. Update existing memories instead of creating avoidable duplicates.
