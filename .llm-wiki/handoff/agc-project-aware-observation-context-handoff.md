# Handoff: AGC project-aware Observation context

## Result

Codex Capture now derives a stable opaque project scope from validated Session cwd metadata, propagates it through Capsule and Observation persistence, and keeps atomic extracted statements self-contained when safe project evidence exists. Quality-first review groups same-receipt observations and expands only exact non-null project scopes, with the confirmed X-publishing case documented as one coherent project proposal.

## Integration State

- Feature commits `f7b4c86`, `6ee4b04`, `ce54a93`, `bb24171`, and verification commit `d552951` were fast-forward merged locally into `main`.
- The Codex-managed worktree and its branch remain present because the workspace is host-owned and must not be automatically removed.
- No GitHub push, release, package build, installation, production model call, historical rewrite, or formal-memory promotion was performed.

## Verification

- record: `.llm-wiki/verification/agc-project-aware-observation-context.md`
- feature worktree: 582 passed in 33.01 seconds
- merged `main`: 582 passed in 36.90 seconds
- compileall, diff whitespace, and strict UTF-8/no-BOM gates passed
- verification authority: passed-agent-local; no CI or independent reviewer claim

## Residual Risk

- Cwd aliases and project moves can produce conservative false-negative scope splits.
- A shared cwd is only a review candidate boundary, never sufficient evidence to merge unrelated memories.
- Historical null-scope Observations remain unchanged.

## Next Action

Use a separate explicit gate if the user wants a new Runtime release/install, GitHub push, or an authorized production Capture/formalization run. The local implementation itself is merged and archived.
