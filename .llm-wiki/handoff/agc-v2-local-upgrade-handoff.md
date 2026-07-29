# Handoff: agc-v2-local-upgrade

## Result

Agent Global Context v2 is implemented, installed locally, migrated, validated, and
configured for Codex on `main`.

## Active Local State

- one public Skill: `C:\Users\admin\.agents\skills\agent-global-context`
- Runtime venv: `C:\Users\admin\.agent-global-context-runtime\venv`
- MCP executable: `C:\Users\admin\.agent-global-context-runtime\venv\Scripts\agc-mcp.exe`
- active v2 memory root: `C:\Users\admin\.agent-global-context-v2`
- retained v1 root: `C:\Users\admin\.agent-global-context`
- v1 auto capture: disabled

## Memory State

- 19 formal schema-v2 memories
- one candidate
- one core card: the explicit difficult-but-correct decision standard
- personal facts remain scoped or discoverable rather than automatically exposed
- current AI/Skill/Agent/LLM interest is evolving with a review date
- memory-system North Star and Codex coverage are explicit goal-bound memories

## Boundaries Preserved

- The LLM chooses whether memory is relevant and whether to call the tools.
- Runtime supplies deterministic validation, storage, idempotency, migration, backup,
  lifecycle, and Hard Forget.
- No P0/P1 automatic prompt injection remains.
- Sensitive and secret persistence remains disabled.
- Trace/Eval/Loop and LLM Wiki Runtime are not integrated.
- Codex task capture and historical backfill are not enabled by this delivery.

## Verification

- evidence: `.llm-wiki/verification/agc-v2-local-upgrade.md`
- result: repository, install, migration, CLI, MCP stdio, encoding, backup, and noise gates passed
- trust level: agent-local plus independent review agents
- restart required: yes

## Rollback

1. Restore the timestamped Codex config and Skill directories from
   `C:\Users\admin\.agent-global-context-runtime\backups\20260730-033200-562-ccbe4d2edc7a4536a947db8ea82c35f7`.
2. If v1 capture is intentionally re-enabled, restore its backed-up `config.yaml` from
   `C:\Users\admin\.agent-global-context-v1-backups\20260729T192524374Z-226c14fce34848bbaea3ced7078ba214`.
3. Keep the v2 root and Runtime install until rollback is verified; do not delete them as
   part of the first rollback step.

## Next Action

Start a new Codex task or restart Codex so the new Skill catalog and MCP registration are
loaded. Then optimize the deferred Codex capture path for recent/new tasks with bounded
token cost, failure-open behavior, and no automatic prompt injection.
