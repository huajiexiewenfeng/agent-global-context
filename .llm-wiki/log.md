# LLM Wiki Log

## 2026-07-29 — agc-v2-runtime-foundation

- Flow Record moved from execution to archived completion.
- Runtime Foundation implemented in commits `1ab7ba0` through `4a01076`.
- Agent-local release gate passed: 94 tests, wheel/sdist build, CLI version, strict UTF-8/no-BOM scan, and `git diff --check`.
- Verification and handoff registered under `.llm-wiki/verification/` and `.llm-wiki/handoff/`.
- No dashboard was created because this repository has no enabled or registered progress dashboard.
- Next independent deliverable: v2 Recall/Skill Adapter.

## 2026-07-29 — agc-v2-local-upgrade

- Flow Record moved from implementation to archived completion.
- One public Skill and the three-tool MCP adapter replaced the five alpha Skill surface.
- Deterministic v1 migration, manifest integrity, path containment, shared-source Hard
  Forget, retry recovery, and repeatable local installation were independently reviewed.
- Agent-local release gate passed: 188 tests, wheel/sdist build, CLI, MCP 2.0 stdio,
  strict UTF-8/no-BOM, backup ZIP, no-op installer, and local cutover checks.
- Local v2 contains 19 formal memories and one candidate; exposure is limited to one
  core card, with no personal core cards.
- v1 remains rollback material with auto capture disabled.
- Capture/backfill, Trace/Eval/Loop, and LLM Wiki Runtime remain deferred.
- No dashboard was updated because this repository has no enabled or registered progress dashboard.
