# Capture review read contention

- bug_id / flow_id: 2026-09-07-capture-review-read-contention
- status: follow-up-installed-awaiting-restart
- documentation_mode: new Bug Brief; preserve unrelated active RSI changes
- routing: project-develop-copilot -> project-fix -> systematic-debugging

## Symptom and expected behavior

Two September 6 review tasks processed the same ten-observation digest. The earlier task reported nine capture_read_busy errors and one unfinished read. The later task generated three previews, but each observation read took roughly 33–45 seconds. A subsequent explicit status check returned busy twice. Existing preview content is present; zero data is not established.

Expected: review existing committed observations with bounded latency and honest busy/error handling; no loss of integrity checks, no automatic memory promotion.

## Current evidence

- capture_get and capture_review_status both call CaptureStore.read_snapshot, which holds the same exclusive Capture writer lock through observation, receipt, ledger, Census and integrity decoding.
- Production directory metadata at investigation: 3,303 receipts, 3,303 ledgers, 206 observations, 34 review receipts, 981 frozen Census runs.
- Live lock owner was verified as the scheduled production `agc-capture cycle --once --max-items 10` process; not the offline RSI experiment. Lock remained unchanged across several inspections; exact blocked stack has not been obtained.
- Git history places these read paths in August, before the September offline RSI work. The installed 0.4.5 source contains the same full-snapshot route.
- Hypothesis: repeated global validation and long background critical sections amplify contention as historical batches accumulate. Component timings are in progress; do not claim a specific subroutine is the live lock owner's current stack.
- Component timings confirmed: 981 run manifests / 1,028,000 memberships took 23.637 seconds; canonical catalog / 3,303 unique revisions took 14.154 seconds. This matches the review's per-item latency.

## Approved repair slice

User requested implementation. First replace exact `capture_get` full-snapshot decoding with a bounded committed-receipt read under the existing root lock. Validate identifier, filename binding, complete receipt, manifest/count, every manifest member, ledger binding, and review binding. Missing/corrupt data returns existing safe errors. No cache; Hard Forget remains serialized by the same lock. Search/status keep full integrity semantics in this slice; do not claim their Census or live-writer contention is eliminated. Add regression and I/O-bound tests before implementation.

## Scope and plan

- Active: AGC read/store performance diagnosis and regression-backed minimal fix.
- Read-only: production lock/process metadata and Census catalog timing, existing review task outputs.
- Excluded: deleting locks/data, interrupting the live Runner, disabling Capture, changing formal memory, model calls, installation or Git push without rollout review.
- First isolate component cost without acquiring the global lock or invoking catalog rebuild. Then decide whether a bounded observation read or catalog optimization preserves the existing corruption and Hard Forget contracts.
- Verification must include unchanged safety behavior, no stale/deleted observations, concurrent writer behavior, and fresh latency evidence. No fix implemented yet.

## Flow Record

| Step | Status | Evidence |
| --- | --- | --- |
| source | done | Explicit user report and two task outputs |
| design | active | Full-snapshot amplification and live Runner lock confirmed; component profiling pending |
| plan | pending | Choose smallest fix after profiling |
| development | partial | Exact reads now validate one committed receipt, without global Census traversal; status/search retain global integrity semantics |
| testing | passed-scoped | 118 exact/read/Hard Forget/formal-forget/notification tests passed in 57.59 seconds |
| archive | pending | Production remains unchanged |

## Authorized installation — 2026-09-07

- Local 0.4.5 repair installed through the existing immutable installer; deployment `3345a0e80d67b60121a38b1a48d06fa6e47be0ee96cb2091715321339b985bc5`. Old `b4828f7e...` environment retained.
- Installation source was a clean HEAD export with only `capture_store.py` and `capture_read_service.py` overlaid. Installed Skill bytes and existing dependency versions were preserved; experimental RSI modules are absent from the installed package.
- Installer exit 0; new environment import/entry-point validation and `pip check` passed. Installed repair file SHA-256 values match the tested source: `931d91a66d70f22dc1a76524deb026d2fcb3a4c2000a776f0efc8f50616956d6`, `82880090f47c159826879c690d877f2cf8cfad63e4156cfba52d05e1aa2bad4b`.
- MCP/Capture/Hook launcher targets switched. Capture launcher retains the existing Trace DB path; scheduled task remains enabled with the same action and arguments. No manual model cycle started. Existing running processes were not interrupted.
- All 36 formal memory file hashes and the Memory Root config hash are unchanged. Trace DB remains present at its existing path; no migration/reset was performed.
- Installer backup retained under backup batch `20260907-151847-010-acdc32e33c5e4b58b01ca52f8eeec7e7`.
- User will restart Codex. Host-loaded MCP acceptance remains pending; a pre-restart task may still use the old server. No Git commit/push or published version release.

## Verified result and remaining boundary

- Rollout authorization: user explicitly approved installation and will restart Codex afterward. Stage a clean HEAD export with only the two repaired runtime files, excluding all untracked RSI experiments. Preserve installed Skill bytes and pin existing dependency versions. Use the existing immutable local installer, preserve Memory Root/Trace database/Runner task and old deployment. This is a local 0.4.5 repair distinguished by deployment fingerprint, not a GitHub release.

- RED: no-global-snapshot test failed; two additional tests showed old exact reads exposed observations despite a corrupt ledger or review record. GREEN: all six new tests and the adjacent safety suite pass.
- Added `CaptureStore.read_committed_receipt`; exact read uses at most eight manifest members and retains the existing writer/Hard Forget lock. No content cache or global healthy claim.
- Read-only timing against the explicitly identified production observation through the new source path: 0.0561 seconds, observation present. No content printed and no production files installed. This is one fresh timing sample, not a concurrency benchmark or complete rollout acceptance.
- Background writers can still cause legitimate busy responses. `capture_review_status`, search and Runner full Census accounting have not changed; this slice does not solve their growth cost. Do not report the entire incident permanently resolved.
- Next gate: review scoped diff, approved production rollout/restart and live review acceptance; separately scope Census critical-section optimization if status latency remains unacceptable. Do not overwrite the running installation or delete its locks.

## Follow-up — 2026-09-19

- New evidence: scheduled review checks still returned `capture_read_busy` while successful status reads repeatedly surfaced the same zero-proposal batch.
- Root causes: status still used the global Census-bearing snapshot under the writer lock; scheduled review left `discard` and `needs_context` outcomes unrecorded even when a batch produced no formal-memory proposal.
- Implemented repair: status uses a lock-free, committed-receipt review snapshot that validates receipt, ledger, manifest, observation, and review bindings while omitting Census. Exact content reads remain writer-locked. A zero-proposal scheduled review records only `discard` / `needs_context` review receipts, never formal memory.
- Verification: the writer-lock regression failed before the change and passed afterward; 67 adjacent Capture/Skill tests and 12 MCP tests passed. A read-only production-root sample returned healthy status in 1.296 seconds without exposing observation content; the prior first implementation scanned all receipts and took 32.042 seconds, so it was narrowed to observation-referenced receipts before acceptance.
- Installed deployment: immutable Runtime `84498f12cbf8f7691b0ece5533cb1cbacb0193e1eabe1e454e2fd481d0bd5479`; source/installed hashes match for both changed Runtime files and both Skill workflow files. `agc-mcp --version` reports 0.4.5 and `pip check` reports no broken requirements. The Capture launcher retains `C:\Users\admin\.agent-trace-runtime\trace.sqlite3`.
- The installer initially refused the existing unmarked MCP table. The unchanged table was wrapped in the installer's two management comments after a byte-for-byte backup at `backups/20260919-managed-config-marker/config.toml`; the rerun then completed and created its normal backup batch `20260919-200036-697-e8cddd92796d4b6b9df2b43b61d987dd`.
- Installed read-only acceptance is healthy; after the cold first run, two consecutive production-root status reads completed in 1.341 and 1.316 seconds. No formal memory or review receipt was changed during verification.
- Remaining gate: restart Codex and verify the newly loaded MCP process. The prior immutable Runtime remains available for rollback.
