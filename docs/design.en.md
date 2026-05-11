# Agent Global Context Design

## Purpose

Agent Global Context is a Markdown-first global context layer for AI agents. It preserves key information that should influence future agent behavior across sessions: user background, technical preferences, coding habits, work environment, and project knowledge.

Memory files are the storage mechanism. The actual product goal is agent global context: durable understanding that helps the agent make better future decisions.

## Non-Goals

- It does not store complete chat logs by default.
- It does not replace the agent context window.
- It does not require a database, vector store, or background service in the MVP.
- It does not treat inferred personal judgments as long-term truth.

## Principles

1. Key context over total memory.
2. Markdown content, YAML configuration.
3. Recall by priority and relevance.
4. Explicit source and confidence on long-term memory.
5. Sensitive or high-impact personal memory requires confirmation.
6. `P0-P2` long-term memory must explain why it matters; `P3-P4` rationale is recommended when useful.

## Priority Model

- `P0`: user background, stable identity-level context, language preference, durable collaboration needs.
- `P1`: technical preferences, tool preferences, architecture preferences, workflow preferences.
- `P2`: coding style, testing habits, review habits, branching and commit conventions.
- `P3`: project knowledge, environment knowledge, commands, dependencies, architectural decisions.
- `P4`: current task state, session summaries, next actions, blockers.

## Recall Model

Recall begins at `index.md`, then reads context by priority:

- `P0`: read a short recall summary by default.
- `P1`: read when discussing technical choices, tools, or collaboration flow.
- `P2`: read for code writing, review, testing, refactoring, and implementation work.
- `P3`: read when the current working directory or user request maps to a project.
- `P4`: read only when continuing recent work or restoring session state.

## Write Model

Writing has four conceptual stages:

- `observe`: detect possible context value.
- `stage`: store a candidate in staging.
- `commit`: write a confirmed or high-confidence item to long-term memory.
- `reject`: explicitly avoid storing or mark as rejected.

MVP implements recall, commit, alpha auto capture, and candidate review.

Auto capture is enabled by default. It only writes candidates to staging and never creates long-term memory directly. Users can disable it in configuration.

Staging files are included in the template, but MVP agents should use them only when the user explicitly asks to stage a memory or when a sensitive/high-impact candidate should not be committed yet.

## Auto Capture

Auto capture is the alpha implementation of the `observe` stage.

When enabled, the agent may identify signals with possible long-term value and write candidate entries to `staging/inbox.md`. Auto capture only creates candidates. It never creates long-term memory directly.

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

Candidate entries should include source, proposed priority, proposed confidence, rationale, creation time, and status.

Sensitive filtering applies during observe. Secrets and credentials must not enter staging. Personal sensitive context should go to pending review only if it may be legitimate to remember and the user is asked. Unconfirmed psychological or personality inferences should be dropped by default.

`staging/inbox.md` is not part of default recall. Candidates are not long-term facts.

Operating principle:

```text
Auto capture may notice.
Staging may hold.
Review may approve.
Commit may remember.
Recall must not trust unconfirmed candidates.
```

## Candidate Review and Promotion

Candidates enter formal memory through review and commit.

```text
auto_capture
  -> staging/inbox.md or staging/pending-review.md
  -> review
  -> commit
  -> long-term memory
```

Review outcomes:

- `promoted`: accepted and committed to long-term memory.
- `rejected`: rejected by the user or policy.
- `expired`: not reviewed within the retention period.
- `pending`: still waiting for review.

Promotion rules:

- `confirmed`: can be promoted.
- `observed`: can be promoted when non-sensitive and reliable.
- `inferred`: requires user confirmation.
- `tentative`: requires confirmation or repeated evidence.

When a candidate is promoted, its staging entry should record `promoted_to`, `reviewed_at`, and `status: promoted`.

The agent should suggest review when candidate volume or age crosses configured thresholds, for example when there are at least 5 pending candidates or the oldest pending candidate is at least 7 days old. Review prompts should be non-blocking unless sensitive/high-impact confirmation or expiration is required.

## Recall Budget

Priority decides importance, relevance decides inclusion, and budget decides depth. When multiple priorities match, agents should load summaries first and detailed entries only when needed.

Default order:

1. `index.md`
2. `P0` `Recall Summary`
3. matching project `P3` summary
4. relevant `P1/P2` summaries
5. `P4` active state only for continuation

Old session details should be dropped before active project context or directly relevant preferences.

## Confidence

Use four confidence values:

- `confirmed`: explicitly stated, approved, or requested by the user.
- `observed`: supported by reliable files, command output, configuration, or repeated visible behavior.
- `inferred`: derived by the agent but not directly confirmed.
- `tentative`: weak, ambiguous, or likely temporary.

## Project and Dedupe Rules

Project-scoped memory should resolve a stable project id from `index.md` `Project Map`, then Git remote slug, then current directory slug. New or ambiguous project ids require confirmation.

User-confirmed project bindings are authoritative and should be checked before heuristics such as Git remote slug or directory name.

Before appending a memory item, the agent should scan the target file for an existing memory with the same meaning. Update existing memories when possible, and use `status: superseded` when new information replaces old information.

## Conflict and Lifecycle Rules

Current user instructions override stored memory unless unsafe or impossible. In an active project, confirmed project conventions and decisions override general personal preferences.

`P4` is temporary. Active state should be updated in place, completed next actions should be removed, and stale blockers should not be carried into unrelated tasks.

## Sensitive Memory

Sensitive personal information, secrets, credentials, private keys, financial information, medical information, or unconfirmed psychological/personality inferences must not be silently written to long-term memory. Ask the user whether to write it, stage it for review, or skip it.
