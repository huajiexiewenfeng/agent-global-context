# Handoff: 2026-08-01-catalog-stale-after-write

## Result

AGC formal-memory writes now keep the generated JSON/Markdown catalog and
progressive read surfaces consistent without requiring the LLM to remember a
separate admin rebuild.

## Changed Behavior

- Accepted formal-memory responses that contain a `memory_id` refresh the catalog.
- Candidate-only observations do not trigger unnecessary catalog generation.
- Hard Forget retains its existing transactional catalog handling.
- If post-commit catalog refresh fails, the formal write remains `accepted` and
  returns the stable warning `catalog_refresh_failed`; callers can run
  `agc.admin validate/rebuild_catalog` without repeating a write that already
  persisted.
- The public tool contract documents the new consistency and warning semantics.

## Active Local State

- Codex config points to Runtime venv:
  `C:\Users\admin\.agent-global-context-runtime\venvs\0918faf66cdba6eb6eab33d182fd192bbeca6e6ce1815f3f248f5ff67f6145ee`
- Previous Runtime venv remains available:
  `C:\Users\admin\.agent-global-context-runtime\venvs\753035ae1f47ac63d11544f62a3992dccc726183fc77d88a0a3cd70041815f87`
- Active memory root: `C:\Users\admin\.agent-global-context-v2`
- Installer rollback backup:
  `C:\Users\admin\.agent-global-context-runtime\backups\20260801-220759-349-f644e8ba966b4fc0b20bcf7e2a77d601`
- Restart required: yes; the current task's already-loaded MCP process is not hot-swapped.

## Memory State

- 20 formal memories are valid and searchable.
- 16 formal memories came from the v1 migration.
- Four formal memories were created after the v2 upgrade.
- One candidate remains outside the formal catalog.
- No candidate body or personal memory body is copied into repository evidence.

## Verification

- Evidence: `.llm-wiki/verification/2026-08-01-catalog-stale-after-write.md`
- Repository result: `190 passed in 287.24s`; `git diff --check` passed.
- Installed Runtime smoke test: passed without manual rebuild.
- Live root: validation accepted with zero invalid items; overview/search both 20.
- Trust level: agent-local.

## Residual Risk

- Read-time self-healing for out-of-band edits is intentionally not part of this fix.
- Automatic Codex task capture/backfill coverage remains a separate AGC objective;
  this change repairs recall consistency but does not itself increase capture volume.

## Next Action

Choose how to integrate branch `fix/catalog-consistency`, then start a new Codex
task or restart Codex so MCP calls use the newly configured Runtime.
