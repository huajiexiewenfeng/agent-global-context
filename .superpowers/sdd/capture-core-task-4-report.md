# Capture Core Task 4 Report

## Scope

Implemented isolated explicit Capture read views and status diagnostics. Capture
remains disabled; no source scan, transcript read, Hook, model, network, or
scheduler behavior was added.

## Delivered

- `agc.read` actions: `capture_overview`, `capture_search`, `capture_get`.
- `agc.admin` action: `capture_status`; public MCP tool count remains exactly
  three because the existing host-bound dispatcher routes these actions.
- Capture coverage uses CaptureKey sets, 0..1 ratios, raw counts, and the
  required `not_applicable` empty inspection denominator. Unkeyed source
  quarantine degrades health and prevents a complete-source claim.
- Search supports the specified filters, signed versioned opaque cursors,
  stable `captured_at DESC, observation_id ASC` pagination, default 20 and
  maximum 100. Only complete Receipts with valid immutable manifests expose
  observations.
- Capture source output is redacted to stable identifiers only: it omits paths,
  hashes, locators, extractor raw data, and runtime transaction metadata.
- Status reports only safe configuration/runtime/root fingerprints, source-root
  IDs, extractor boundary, budgets, state, and route conflicts.

## Verification

```text
pytest tests/test_capture_read_service.py tests/test_capture_status.py \
  tests/test_mcp_server.py tests/test_catalog_and_read.py \
  tests/test_capture_store.py tests/test_capture_transaction.py \
  tests/test_admin_service.py -q
75 passed

python -m compileall -q agc_runtime
git diff --check
strict UTF-8 / no-BOM check for all Task 4 changed files
```

## Residual concern

Source census production and host route discovery are intentionally deferred to
the later Source/Host plans. This core reads only the strict, content-free
artifacts available today and reports activation as not ready.
