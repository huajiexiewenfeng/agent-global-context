# Capture Source Census Task 3 Brief

## Goal

Add a metadata-only Codex Stop Hook and immutable dirty spool. The Hook is a
foreground-latency hint only; Scanner reconciliation remains correctness
authority. It must always fail open and must never persist task content.

## Files

- Create `agc_runtime/capture_dirty.py`
- Create `agc_runtime/capture_hook.py`
- Create `tests/test_capture_hook.py`
- Modify `pyproject.toml`
- Modify `tests/test_cli_contract.py`
- Create `.superpowers/sdd/capture-source-task-3-report.md`

## Required contract

- Add entry point `agc-capture-hook = "agc_runtime.capture_hook:main"` with
  operation form `agc-capture-hook --root <memory-root>`; the future host
  launcher binds that exact root.
- Consume Stop stdin fields including `session_id`, `turn_id`,
  `transcript_path`, `cwd`, `hook_event_name`, `model`, `stop_hook_active`, and
  `last_assistant_message`.
- Persist only schema/adapter/root versions, opaque source-root/task/revision
  identity, validated relative transcript locator or null, observed time, and
  Hook event. Never persist last message, prompt, model output, model name,
  cwd, raw source root, transcript content, or absolute path.
- Never open/read the transcript in Hook code. Never import Scanner, Store,
  extractor, MCP, or formal write service.
- Dirty spool uses one event per unique fsynced same-directory temporary file,
  then an atomic no-overwrite install (hard-link on current Windows/NTFS);
  never shared append-only JSONL. If that primitive is unsupported or fails,
  the Hook remains silent and failure-open and Scanner coverage remains
  authority. A destination collision preserves the existing marker. Stable
  key plus nonce names the marker; duplicate markers are harmless and deduped
  later.
- Write strict UTF-8 JSON, fsync where supported, atomically install; no stdout
  or stderr output that could affect foreground task.
- Validate locator resolves inside configured source root; path escape and
  reparse escape yield null/no marker as specified without foreground failure.
- Malformed stdin, path escape, reparse escape, collision, permission failure,
  and disk failure all remain failure-open. Scanner correctness must not depend
  on marker success.
- Scan the entire synthetic memory root for sentinel last-message content and
  require zero hits.
- No Source enumeration, Scanner execution, model, network, semantic Capture,
  or activation behavior.

## TDD and verification

Record RED for hook/CLI tests, then minimal GREEN. Run related/full tests,
package an installed hook entry point, verify silent exits and root binding,
run compile/diff/strict UTF-8 gates, report evidence, and commit with
`feat: add metadata-only capture hook`.
