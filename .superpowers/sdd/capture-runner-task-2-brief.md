# Capture Extractor/Runner Task 2 Brief

## Scope

Implement only the strict extractor DTO/schema boundary and the isolated Codex
reference adapter from Task 2 of the approved Extractor/Runner plan. This task
does not implement Runner state, durable token reservations, persistence, Hook
installation, profile activation, or a real model invocation.

## Contract decisions

- `capture_extractor.py` owns content-hidden DTOs for extractor description,
  capability probe, collected draft, and extraction result, plus the stable
  `SemanticExtractor` Protocol.
- The future Task 3 `TokenReservation` remains a forward protocol annotation;
  Task 2 does not modify `capture_contracts.py` or invent durable accounting.
- Extractor JSON is exactly one final payload with schema version
  `capture-extractor-v1` and `drafts` containing zero through eight items.
  Draft fields and enums intentionally match the already-reviewed Task 1
  `ObservationDraft` mapping so the Runner can pass `to_mapping()` into the
  existing persistence gate without an adjacent interface change.
- JSON, DTOs, events, usage, and subprocess outcomes are fail-closed. Duplicate
  or unknown keys, missing keys, booleans in integer fields, NaN/infinity,
  invalid Unicode scalars, malformed JSONL, multiple finals, and unsupported
  events are rejected with only `stage/code/retryable` exposed.
- Absent or partial provider usage yields `usage=None`; Task 3 will consume the
  conservative reservation. Invalid complete usage is an output failure.
- The Codex command is an argv tuple with `shell=False`. The Capsule is canonical
  JSON on stdin only. The child cwd is a newly created empty temporary directory;
  the static output schema remains outside it and no content file is created.
- Child environment is an explicit allowlist. AGC Hook/profile variables,
  `CODEX_HOME`, `PYTHONPATH`, and other activation variables are not inherited.
  Provider authentication variables may be forwarded by exact allowlist.
- Stdout and stderr are independently bounded while the child runs. Raw bytes,
  model text, stderr, exception strings, Capsule content, and executable paths
  never enter DTO repr, errors, logs, or return metadata.
- Capability activation requires successful version and help checks for every
  required flag plus a content-free ephemeral smoke invocation. Any missing
  capability returns an unavailable content-free probe.

## Test boundary

All process integration uses `tests/fixtures/fake_codex_exec.py` as a real child.
No live Codex profile, network, real provider, model, MCP, Skill, Hook, or Memory
Root is accessed. The fake validates argv/cwd/env/stdin internally and persists
nothing.
