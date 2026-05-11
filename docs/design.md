# Agent Global Context Design

## Purpose

Agent Global Context is a Markdown-first global context layer for AI agents. It preserves key information that should influence future agent behavior across sessions: user background, technical preferences, coding habits, work environment, and project knowledge.

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
6. Every long-term memory item should explain why it matters.

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

MVP implements recall and commit. Active capture and review are planned follow-up skills.

## Sensitive Memory

Sensitive personal information, secrets, credentials, private keys, financial information, medical information, or unconfirmed psychological/personality inferences must not be silently written to long-term memory. Ask the user whether to write it, stage it for review, or skip it.

