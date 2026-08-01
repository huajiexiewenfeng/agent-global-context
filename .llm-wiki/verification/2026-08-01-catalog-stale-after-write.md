# Verification: 2026-08-01-catalog-stale-after-write

## Result

- status: passed-agent-local
- executor: Codex agent-local
- authority: agent-local
- scope: write/catalog consistency, progressive reads, Runtime integration,
  installed artifact, and current host-bound memory root
- raw_output_ref: current Codex task command output on 2026-08-01
- limitation_acceptor: not applicable; no verification limitation was accepted

## Repository Evidence

- Clean baseline before implementation: `188 passed in 344.28s`.
- Targeted RED: exactly two expected catalog-consistency failures and 11 passes.
- Targeted GREEN: `13 passed in 1.60s`.
- Write plus Runtime end-to-end integration: `18 passed in 6.25s`.
- Final command:
  `C:\tmp\agc-catalog-fix-test-venv\Scripts\python.exe -m pytest -q --basetemp C:\tmp\agc-pytest-final-20260801-run2`
- Final result: exit code 0, `190 passed in 287.24s`.
- `git diff --check`: exit code 0; only the repository's expected LF-to-CRLF
  conversion warnings were emitted.

## Test Integrity

- production_changes: `agc_runtime/write_service.py`
- test_changes: write-service regression and Runtime vertical-slice assertions
- mocks_or_fixtures_changed: none
- assertions_added_or_removed: assertions added for both generated catalog files,
  overview/search visibility, validation, and failure-warning semantics
- expected_behavior_changed: accepted formal writes now refresh derived catalogs
  automatically; a failed refresh preserves the accepted source-of-truth write
  and adds `catalog_refresh_failed`
- over_mocking_risk: low; the main regression and end-to-end tests exercise real
  filesystem writes and catalog reads, while one focused monkeypatch covers the
  derived-refresh failure branch

## Installed Runtime Evidence

- Installed content-addressed venv:
  `C:\Users\admin\.agent-global-context-runtime\venvs\0918faf66cdba6eb6eab33d182fd192bbeca6e6ce1815f3f248f5ff67f6145ee`
- Installer completed package build, final-path import/MCP checks, configuration
  switch, and retained the prior venv for rollback.
- Isolated installed-artifact smoke test performed init, formal write, validate,
  overview, and search without calling rebuild: accepted, zero warnings,
  validation accepted, count 1, and the new ID was immediately searchable.
- The temporary smoke root and helper scripts were removed after verification.

## Live Memory Evidence

- New installed Runtime validated
  `C:\Users\admin\.agent-global-context-v2` with `invalid_count=0`.
- Overview reported 20 formal memories.
- Search returned the same 20 formal memories.
- No test memory was written to the live root.

## Residual Risk

- This Codex task retains the MCP process loaded before installation. New tasks or
  a Codex restart load the configured fixed Runtime.
- Manual out-of-band edits or a process failure after a committed formal write can
  still stale derived catalogs. `agc.admin validate/rebuild_catalog` remains the
  deterministic repair path; read-time self-healing is a separate follow-up.
- No CI or external reviewer result is recorded, so verification trust remains
  `agent-local`.
