# Recall Policy

## Goal

Load enough context to guide behavior without recreating context explosion.

## Workflow

1. Read `config.yaml` if present.
2. Read `index.md`.
3. Load `P0` recall summary for substantial work.
4. Classify the current request.
5. Load only relevant `P1-P4` files.
6. Prefer `Recall Summary` sections before detailed entries.
7. Report briefly which memory files were loaded.

## Task Triggers

- Technical planning: load `P1`.
- Code implementation or review: load `P1` and `P2`.
- Environment or command work: load `P3` environment files.
- Project work: load matching project `P3`.
- "Continue", "resume", "last time": load project `active.md` and recent session summaries.

## Guardrails

- Do not load every memory file by default.
- Do not load old sessions unless the user asks or `active.md` points to them.
- Do not treat tentative or inferred memory as confirmed.
- Mention stale, contradictory, or low-confidence memory when it affects the task.

