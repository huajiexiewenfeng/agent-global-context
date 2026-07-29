# Verification: agc-v2-local-upgrade

## Provenance

- executor: agent-local with independent read-only implementation reviews
- date: 2026-07-29
- authority: user-authorized direct `main` upgrade and local cutover
- limitation_acceptor: none required
- raw_output_ref: Codex task tool outputs and ignored `.superpowers/sdd/` review packages
- final_test_output: `D:\tmp\agc-final-188-2d6f4e10\pytest.out`
- exit_code: 0

## Repository Gate

```text
focused installer gate
41 passed

full repository gate
188 passed in 264.32s

python -m build
Successfully built agent_global_context_runtime-0.2.0.tar.gz
and agent_global_context_runtime-0.2.0-py3-none-any.whl

wheel metadata
version = 0.2.0
mcp optional dependency = mcp==2.0.0

git diff --check
exit 0

strict UTF-8 and no-BOM
all changed repository text passed
```

Task 1, Task 2, and Task 3 each used a fresh implementer and independent reviewer.
Every Critical/Important review finding was fixed and re-reviewed before local mutation.
The final whole-range review approved direct `main` push after evidence was made
non-semantic and Runtime upgrades became inactive, content-addressed, final-path
validated, and rollback-safe.

## Installed Runtime and Adapter

```text
agent-global-context-runtime 0.2.0
mcp 2.0.0
pip check: No broken requirements found.

official MCP stdio client:
tools = [agc.admin, agc.read, agc.write]
is_error = false
overview_status = accepted
memory_count = 19
```

The active Codex config parses as TOML and contains exactly one marked
`mcp_servers.agent_global_context` block. Its command is the final-path validated
content-addressed `agc-mcp.exe`, and `AGC_MEMORY_ROOT` is the parallel v2 root.

## Local Cutover Gate

```text
active AGC Skill directories: 1
retired alpha Skill directories in timestamped backup: 4
installer no-op rerun backup_path: null
agc.admin validate: accepted, invalid_count 0
formal memories: 19
candidates: 1
v2 backup ZIP testzip: ok
v1 files: 16
v1 frozen manifest SHA-256:
a9efe4fb81c9ff899bf2822f41af058a5b65640d99b299f12978b27090cb341f
```

Migration receipt:

- source count: 16
- snapshot count: 7
- ignored count: 9
- excluded-sensitive count: 0
- migrated formal memories: 16
- current-task confirmed formal memories: 3
- candidates: 1

Recall/noise distribution:

- core card: 1
- scoped cards: 14
- discoverable-only: 3
- history-only: 1
- personal: 4, with zero personal core cards
- sensitive/secret persistent items: 0

Progressive-read smoke:

- overview returned counts but no automatically injected cards
- one scoped search returned one eligible card
- unrelated `sourdough weather forecast` search returned zero items

## Encoding and Rollback

- v1 was backed up before `auto_capture.enabled` changed to `false`
- v1 was not migrated in place and remains rollback material
- the single v1 BOM source was normalized only in the v2 snapshot
- installed config, launcher, Skill, and all v2 managed text strict-decode as UTF-8 without BOM
- the v2 deterministic backup ZIP passed integrity testing

Rollback locations:

- v1 config backup: `C:\Users\admin\.agent-global-context-v1-backups\20260729T192524374Z-226c14fce34848bbaea3ced7078ba214`
- active config/Skill backup: `C:\Users\admin\.agent-global-context-runtime\backups\20260730-033200-562-ccbe4d2edc7a4536a947db8ea82c35f7`
- content-addressed Runtime switch backup: `C:\Users\admin\.agent-global-context-runtime\backups\20260730-043855-668-1c788d0c5f8847a9beddac4d9810e727`
- v2 Runtime backup: `C:\Users\admin\.agent-global-context-v2\.runtime\backups\agc-backup-52b89fa735c8bb4a2e0974f39b16c1d13161f4a8673f8a805ff35918c18efd46.zip`

## Residual Risk

- The newly registered MCP server is not visible inside this already-running Codex task;
  a new task or Codex restart is required.
- Agent-local verification is not CI-backed.
- Manifest integrity detects corruption but is not a keyed authenticity signature.
- Hard Forget crash recovery intentionally stores no rollback body; an exact authorized
  retry converges using content-free journals and manifest-bound pending state.
- Codex capture/backfill remains intentionally disabled.
