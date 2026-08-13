# Capture Core Task 4 Report

## Scope

Implemented and review-hardened isolated explicit Capture read views and status
diagnostics. Capture remains disabled; no source scan, transcript read, Hook,
model, network, scheduler, or extractor behavior was added.

## Delivered

- `agc.read` actions remain `capture_overview`, `capture_search`, and
  `capture_get`; `agc.admin` remains `capture_status`. MCP still exposes exactly
  the existing three public tools.
- Cursor authenticity uses a durable 32-byte CSPRNG key at
  `.runtime/capture/cursor-hmac-key`, HMAC-SHA256 with constant-time comparison,
  and a versioned payload bound to key ID, canonical MemoryRoot fingerprint,
  normalized filters plus limit, timestamp, and observation ID. The key is
  created by admin init and lazily only when a read must issue `next_cursor`.
- Search validates every filter, enum, UTC-Z time bound, range, and exact
  non-boolean limit before reading data. It sorts parsed instants by
  `captured_at DESC, observation_id ASC`, including fractional seconds and
  stable three-page traversal.
- `CaptureStore.read_snapshot()` holds the Capture root lock and strictly
  decodes receipts, immutable manifests, visible observations, full
  `RevisionRef` census records, tombstones, source quarantines, and conflicts.
  Corrupt/duplicate/orphan objects degrade integrity through fixed content-safe
  diagnostics and cannot create a complete-source or complete-receipt claim.
  The read service no longer scans the private Capture layout.
- Missing and corrupt Capture gets return fixed machine errors without paths,
  statements, raw exception text, or corrupt object content.
- Direct status marks MemoryRoot binding, routes, and extractor capability as
  `not_assessed`. MCP supplies explicit MemoryRoot binding evidence and proves
  only that binding. Source roots expose configured count plus unavailable
  assessment and an empty ID list. Activation remains false with machine
  reasons; the cursor key exposes only readiness and key ID.
- Cursor key bytes are excluded from backup and preserved across restore. This
  is the minimum safe integration needed for the new secret; Task 5 owns any
  future backup-encryption, export, and explicit key-rotation policy.

## Verification

```text
# Initial RED
pytest tests/test_capture_read_service.py -q
12 failed, 9 passed

# Final focused Capture read/status/MCP/admin
pytest tests/test_capture_read_service.py tests/test_capture_status.py \
  tests/test_mcp_server.py tests/test_admin_service.py -q
46 passed

# Related Capture/Admin/MCP/runtime, with wheel case separated because the
# repository venv lacks setuptools
pytest tests/test_capture_transaction.py tests/test_capture_store.py \
  tests/test_capture_status.py tests/test_capture_read_service.py \
  tests/test_capture_paths.py tests/test_capture_contracts.py \
  tests/test_admin_service.py tests/test_mcp_server.py \
  tests/test_runtime_config.py \
  -k "not built_wheel_contains_default_and_installed_admin_init_works" -q
222 passed, 1 deselected

# Separated wheel behavior
# Clean Codex Python: setuptools.build_meta.build_wheel on a disposable source
# copy -> exit 0; wheel contains agc_runtime/default_config.yaml.
# Repository Python: pip --no-deps --target disposable install -> exit 0.
# Isolated PYTHONPATH/PYTHONNOUSERSITE admin init -> exit 0, status accepted,
# cursor-hmac-key created.

python -m compileall -q agc_runtime
exit 0
git diff --check
exit 0
strict UTF-8 / no-BOM gate for all 11 pre-report changed files
exit 0
```

The whole repository run with only the separated wheel test deselected exceeded
the 240-second command limit without producing a result. It is not claimed as
passing; the focused and related suites above are the completed evidence.

## Test integrity

Production behavior is exercised through real `CaptureStore`, admin/read
dispatchers, actual MCP tool calls, filesystem artifacts, and the installed
wheel CLI. Tests use synthetic Capture contracts and clocks only; they do not
mock HMAC verification, snapshot parsing, MCP routing, or persistence. Assertions
cover wrong filter/limit/root, plain-SHA forgery, tampering, cross-instance same
root, key rotation, lazy key creation, strict empty-dataset validation,
fractional timestamp order, tie order, three pages, corrupt/duplicate snapshots,
safe missing/corrupt get errors, direct versus MCP evidence, rogue roots, and
secret non-disclosure.

## Residual concerns

- Task 5 must define an intentional cursor-key rotation ceremony and any
  encrypted export/import policy. Current rotation invalidates outstanding
  cursors by design, backups exclude the key, and restore preserves the local
  key.
- Source census production, extractor capability assessment, route discovery,
  and Windows host supervision remain deferred to the Source/Extractor/Host
  plans. Status does not claim they were assessed.
- Capture is still disabled and is not usable for collection yet.
