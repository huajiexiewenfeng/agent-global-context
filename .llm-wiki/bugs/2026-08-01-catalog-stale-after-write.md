# Bug Brief: 2026-08-01-catalog-stale-after-write

## Summary

- title: Accepted formal-memory writes do not refresh the generated catalog
- status: verified
- flow_id: 2026-08-01-catalog-stale-after-write
- severity: high
- owner: Codex
- updated_at: 2026-08-01

## Routing

- intent: Repair AGC write-to-recall consistency and rebuild the current catalog.
- primary_stage: project-fix
- secondary_bridges: systematic-debugging, test-driven-development, verification-before-completion
- confidence: high
- reason: A persisted Memory Item is retrievable by exact ID but absent from overview/search.
- next_gate: Archive Gate
- routed_at: 2026-08-01

## Source

- path/url/log/user_report: User-requested AGC memory effectiveness audit on 2026-08-01.
- source_proxy: Current MCP responses plus repository source and tests.
- sensitivity: normal; no memory body is copied into this record.

## Symptom

`agc.write` accepted and persisted a formal Memory Item, Event, and Receipt, but
`agc.read overview` and `agc.read search` continued to use a stale generated
catalog and omitted the new item.

## Expected

After an accepted formal-memory mutation, the generated JSON and Markdown
catalogs are refreshed automatically. The new or updated card is discoverable
without requiring the LLM to remember and call `agc.admin rebuild_catalog`.

## Evidence

- `agc.admin validate` returned `validation_failed` with two issues:
  `catalog.json` stale and `catalog.md` stale.
- `agc.read overview` reported 19 memories.
- Exact `agc.read get/history/evidence` accepted
  `project-develop-copilot-high-priority-project`, proving the twentieth item
  and its provenance were persisted.
- `agc_runtime.write_service` delegates formal mutations to `MemoryStore` but
  never calls `rebuild_catalog`.
- Existing tests and the original vertical-slice plan explicitly perform an
  admin rebuild between write and read, so the hidden operational dependency
  is not covered as a defect.

## Reproduction

- status: reproduced
- command_or_steps: Write a new formal memory, then call overview/search without an admin rebuild.
- observed: The exact item exists, while generated catalog reads omit it and validation reports stale catalogs.
- expected: The accepted write is immediately discoverable through overview/search.
- limitation: The reproduction used the live MCP surface for evidence; regression coverage will use an isolated temporary memory root.

## Scope

- active:
  - `agc_runtime/write_service.py`
  - `tests/test_write_service.py`
  - `tests/test_runtime_end_to_end.py`
  - `skills/agent-global-context/references/tool-contract.md`
  - this Bug Brief
- read_only:
  - `agc_runtime/catalog.py`
  - `agc_runtime/read_service.py`
  - `agc_runtime/store.py`
  - `agc_runtime/admin_service.py`
  - existing catalog/read/admin tests
- candidate: none
- excluded:
  - Memory Item schema and policy
  - semantic matching and capture extraction
  - Trace/Eval loops
  - Hard Forget transaction behavior
- escalation_history:
  - 2026-08-01: promoted `tests/test_runtime_end_to_end.py` from candidate to active because the existing vertical slice encoded the obsolete manual-rebuild dependency.
  - 2026-08-01: promoted the public tool contract from candidate to active because catalog-refresh warning semantics are observable to callers.

## Diagnosis

The formal Memory Markdown is the source of truth, while `catalog.json` and
`catalog.md` are generated projections. The public write path commits the
source-of-truth mutation but does not refresh those projections. Because
overview/search load the existing JSON catalog without freshness validation,
the omission persists until a separate admin rebuild occurs.

## External Findings

None. The defect is contained within the AGC Runtime and its host-bound memory
root.

## Fix Plan

1. Add a regression test proving an accepted formal write refreshes both
   catalog projections and is immediately visible to overview/search.
2. Make the public write dispatcher refresh the catalog only for responses
   associated with a formal memory, including idempotent retries that can heal
   a previously stale catalog.
3. Preserve the source-of-truth write result if derived catalog refresh fails:
   return the accepted response with a stable warning instead of falsely
   reporting that a saved write failed.
4. Verify targeted tests, then the full suite.
5. Upgrade the installed Runtime, rebuild the current host-bound catalog, and
   re-run validate/overview/search before changing the reported memory count.

## Verification

- status: passed
- commands_or_checks:
  - Baseline: `python -m pytest -q --basetemp <dedicated C:/tmp path>`
  - Targeted red/green: `python -m pytest tests/test_write_service.py -q --basetemp <dedicated C:/tmp path>`
  - Final: full pytest suite plus live `agc.admin validate` and `agc.read overview/search`
- result_summary: Baseline completed with 188 passed in 344.28 seconds. The
  targeted RED produced exactly 2 expected failures; targeted GREEN completed
  with 13 passed, integration coverage with 18 passed, and the final full suite
  with 190 passed in 287.24 seconds. `git diff --check` passed. The content-
  addressed installed Runtime passed an isolated write/validate/overview/search
  smoke test without a manual rebuild. The live root then passed validation
  with `invalid_count=0`, and both overview and search reported 20 memories.
- limitation: Project `.venv` does not contain pytest; a disposable C:/tmp test virtual environment is used.
- residual_risk: The current Codex task retains the MCP process loaded before
  installation. The configuration now points to the new Runtime, so a Codex
  restart or new task is required before MCP calls use the installed fix.

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | Live MCP stale-catalog evidence and user audit request | 2026-08-01 |
| design | done | Source tracing confirms write-to-catalog gap | 2026-08-01 |
| plan | done | Minimal refresh-and-warning plan recorded above | 2026-08-01 |
| development | done | Write dispatcher refreshes catalog for accepted formal-memory responses and preserves accepted writes with a stable warning on refresh failure | 2026-08-01 |
| testing | done | Baseline 188 passed; RED 2 expected failures; targeted GREEN 13 passed; integration 18 passed; final 190 passed; installed and live checks passed | 2026-08-01 |
| archive | done | `.llm-wiki/handoff/2026-08-01-catalog-stale-after-write-handoff.md` | 2026-08-01 |

## Artifacts

- `.llm-wiki/bugs/2026-08-01-catalog-stale-after-write.md`
- `.llm-wiki/verification/2026-08-01-catalog-stale-after-write.md`
- `.llm-wiki/handoff/2026-08-01-catalog-stale-after-write-handoff.md`

## Open Questions

- Whether stale-read self-healing should be a separate follow-up hardening item
  rather than expanding this minimal normal-write-path fix.

## Residual Risk

Manual out-of-band edits or a process failure after the formal mutation can
still stale a generated catalog. `agc.admin validate/rebuild_catalog` remains
the recovery path unless a later bounded self-healing design is accepted.
