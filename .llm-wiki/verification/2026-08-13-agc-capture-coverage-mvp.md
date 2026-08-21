# AGC Capture Coverage MVP Verification

- status: passed-agent-local
- verification scope: repository and synthetic host only
- live profile: pending explicit authorization

## Production evidence

Capture Core, Codex Source Census, Extractor/Runner, and inert Host rollout are
implemented in Runtime 0.3.0. Host activation now consumes the exact Runtime
authorization digest through the installed `agc-capture activation` route.

## Test evidence

The release verifier enumerates AC-01 through AC-20 exactly once and supports
hash-checked resume after a failed environment gate.

- AC-01 through AC-19: all 19 gates passed; parameterized selectors produced
  41 passing cases. Manifest SHA-256:
  `90d2858e2249fd5882d79da1a9de8fcb42a69f34bfb90f796dc541ca84deafca`.
- AC-20 authoritative full suite: `1255 passed`, one expected adversarial
  duplicate-ZIP warning, `468.18s`; stdout SHA-256
  `dd1d69371c8cdcc1920771e41d2157aaddc00fbd3b94ae8a8bbeec88e2f0cd97`.
- Wheel and sdist build passed. Isolated `pip --target` installation loaded the
  `agent-global-context-runtime` 0.3.0 distribution from the target and proved
  exactly four local entry points: `agc`, `agc-mcp`, `agc-capture`, and
  `agc-capture-hook`.
- `pip check`: `No broken requirements found.` `git diff --check` and strict
  tracked UTF-8/no-BOM passed. Final AC-20 manifest SHA-256:
  `55d855d59950eaeecadbe3998fbbadb17fa4d8b247f2c0d00ccb5f5418870ee4`.
- Verifier contract: `5 passed`; Host/CLI/Activation integration: `40 passed`;
  Skill plus local installer: `57 passed`.

## Authorized local installation verification

- The user-authorized inert local upgrade completed from clean `main` commit
  `8a8f75ae5668a18effdb8e0d16bdfe1610f5f99d` using the stable bundled CPython
  3.12.13 executable. The immutable Runtime deployment is
  `97cda42d20ebd68ecd0db5682f10929466bdadd3b3cad25a1a90ae8073a622e9`;
  the installer retained a rollback backup and reported `restart_required=true`.
- Both user-PATH and dedicated Runtime commands report distribution `0.3.0`.
  The four installed entry points are exactly `agc`, `agc-mcp`, `agc-capture`,
  and `agc-capture-hook`; the installed MCP server exposes exactly
  `agc.admin`, `agc.read`, and `agc.write`.
- SHA-256 comparison against the committed source passed for `capture_cli.py`,
  `capture_extractor.py`, `codex_extractor.py`, `capture_capsule.py`, and
  `capture_safety.py`. Codex configuration points at the same immutable
  Runtime MCP executable.
- Installed defaults remain inert: `capture.enabled=false` and
  `capture.mode=off`. This verification did not read a live task source or
  Memory Root, install/enable a Hook or scheduled task, or invoke a model.
- Installer repair TDD: explicit stable-Python selection plus Python-bound
  deployment keys passed `3` focused upgrade/rollback tests; Windows
  PowerShell 5.1 and PowerShell 7 parsing and `git diff --check` passed.

## Mock and synthetic boundaries

Host configuration, scheduler state, Hooks, Memory Roots, Codex sources, and
Extractor processes use temporary synthetic fixtures. No live Codex profile,
real task transcript, real Hook, real scheduled task, or model is accessed.

## Assertions and behavior

The verifier stops at the first nonzero gate, records only content-free output,
hashes both output streams, rejects known private-content sentinels, and keeps
the live-profile gate explicitly pending rather than inferring authorization.

## Residual risk

Real-profile route ambiguity, Scanner coverage, Hook trust/latency, bounded
Shadow Backfill quality, and continuous incremental authorization remain the
separate human-gated Task 7. These do not change the inert release default.
The local installation may be upgraded while inert, but no claim is made about
the active profile's Census or model behavior until that separate authorization.
