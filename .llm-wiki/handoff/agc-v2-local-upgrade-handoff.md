# Handoff: agc-v2-local-upgrade

## Result

Agent Global Context v2 is implemented, installed locally, migrated, validated, and
configured for Codex on `main`.

## Active Local State

- one public Skill: `C:\Users\admin\.agents\skills\agent-global-context`
- Runtime venv: `C:\Users\admin\.agent-global-context-runtime\venvs\753035ae1f47ac63d11544f62a3992dccc726183fc77d88a0a3cd70041815f87`
- MCP executable: `C:\Users\admin\.agent-global-context-runtime\venvs\753035ae1f47ac63d11544f62a3992dccc726183fc77d88a0a3cd70041815f87\Scripts\agc-mcp.exe`
- active v2 memory root: `C:\Users\admin\.agent-global-context-v2`
- retained v1 root: `C:\Users\admin\.agent-global-context`
- v1 auto capture: disabled

## Memory State

- 19 formal schema-v2 memories
- one candidate
- exposure distribution: one core card, 14 scoped cards, three discoverable-only,
  and one history-only
- four personal items, with zero personal core cards
- zero sensitive or secret persistent items
- no Memory IDs, bodies, or personal semantics are recorded in repository evidence

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

1. Restore the pre-content-addressed Codex config and launcher from
   `C:\Users\admin\.agent-global-context-runtime\backups\20260730-043855-668-1c788d0c5f8847a9beddac4d9810e727`.
2. The initial alpha Skill/config backup remains at
   `C:\Users\admin\.agent-global-context-runtime\backups\20260730-033200-562-ccbe4d2edc7a4536a947db8ea82c35f7`.
3. If v1 capture is intentionally re-enabled, restore its backed-up `config.yaml` from
   `C:\Users\admin\.agent-global-context-v1-backups\20260729T192524374Z-226c14fce34848bbaea3ced7078ba214`.
4. Keep the v2 root and Runtime install until rollback is verified; do not delete them as
   part of the first rollback step.

## Next Action

Start a new Codex task or restart Codex so the new Skill catalog and MCP registration are
loaded. Then optimize the deferred Codex capture path for recent/new tasks with bounded
token cost, failure-open behavior, and no automatic prompt injection.
