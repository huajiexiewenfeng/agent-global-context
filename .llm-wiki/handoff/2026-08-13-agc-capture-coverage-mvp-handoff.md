# AGC Capture Coverage MVP Handoff

## Current state

- Runtime release: 0.3.0
- Code/repository release gate: passed agent-local
- Default Capture state: `enabled=false`, `mode=off`
- Public MCP surface: exactly `agc.read`, `agc.write`, `agc.admin`
- Local executables: `agc`, `agc-mcp`, `agc-capture`, `agc-capture-hook`
- Latest inert local install: commit `8a8f75a`, immutable Runtime deployment
  `97cda42d...a622e9`, version `0.3.0`; Codex restart is required to reload the
  updated MCP process.
- Ordinary Recall isolation: Capture observations remain explicit evidence and
  are never automatically injected or promoted to formal memory.

## Completed implementation

Capture Core, Codex Source Census, Hook dirty marking, reconciliation Scanner,
strict Capsule/Safety, isolated Codex Extractor, token-bounded Runner,
transaction recovery, read/status views, backup/restore, Hard Forget, inert
installation, Runtime activation digest, transactional Windows Host controls,
Hook latency gate, operations documentation, and AC-01..20 verifier are complete.

## Verification

See
`.llm-wiki/verification/2026-08-13-agc-capture-coverage-mvp.md`.
The authoritative full suite is 1255 passed with one expected adversarial ZIP
warning; package/install/entrypoint/pip/diff/text gates pass.
The authorized final local install additionally verified committed-source
hashes, all four entry points, the exact three-tool MCP surface, Codex Runtime
binding, and default `enabled=false` / `mode=off` without reading live data.

## Next human gate

Do not infer permission to inspect or mutate the live Codex profile. The next
step requires a new explicit authorization for Scanner-only deployment against
the displayed Source Root IDs, exclusions, seven-day window, schedule, zero
model-call boundary, and exact activation digest. Hook measurement/trust,
Shadow Backfill, sample review, and continuous Runner each remain separate
later approvals. If no approval is given, leave Capture off; the release remains
usable for existing formal-memory Recall and explicit Capture read/status/forget.

## Rollback

Before Capture data exists, installer rollback may restore the prior binary.
After data exists, pause/disable new processing, retain Runtime 0.3.0 for
read/status/forget, preserve Ledger/data, and use only authorized Hard Forget
for deletion. Do not binary-downgrade a root containing Capture data.
