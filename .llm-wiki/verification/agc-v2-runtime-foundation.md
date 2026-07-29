# Verification: agc-v2-runtime-foundation

## Provenance

- executor: agent-local
- date: 2026-07-29
- authority: agent-local
- limitation_acceptor: none required
- raw_output_ref: Codex task terminal release-gate run immediately before commit `4a01076`
- exit_code: 0

## Release Gate

```text
python -m pytest -q
94 passed in 15.17s

python -m build
Successfully built agent_global_context_runtime-0.1.0.tar.gz
and agent_global_context_runtime-0.1.0-py3-none-any.whl

python -m agc_runtime.cli version
{"schema_version":2,"tool":"agc.admin","action":"version",
 "status":"accepted","data":{"runtime_version":"0.1.0"}}

git diff --check
exit 0

strict UTF-8 and no-BOM scan
83 files passed
```

## Scope

- Schema v2 and canonical Markdown.
- Cross-platform locking, atomic writes, transaction recovery, and exact source-key idempotency.
- Observation policy, sensitivity gates, lifecycle transitions, candidates, and write actions.
- Catalog, progressive reads, Hard Forget, validation, deterministic backup, and Tombstone-aware restore.
- Three CLI adapters and the end-to-end init/write/rebuild/search/forget flow.

## Test Integrity

- production_changes: yes
- test_changes: yes
- mocks_or_fixtures_changed: fixtures added; monkeypatch used only for explicit disk, event, cleanup, and restore failure injection
- assertions_added_or_removed: assertions added; the original two CLI contract assertions remain
- expected_behavior_changed: new v2 Runtime behavior added
- over_mocking_risk: low
- evidence: filesystem behavior uses real temporary directories; CLI behavior uses real subprocesses; backup/restore uses real ZIP files

## Residual Risk

- Verification is not CI-backed and has not received external code review.
- Recall/Skill Adapter, Codex side-channel capture, and v1 migration are intentionally outside this delivery.
