# Capture Operations

Capture is an optional evidence pipeline for completed Codex tasks. It can
collect reviewable observations and classify them, but those observations are
not formal memory, are not automatically injected into prompts, and are not
automatically promoted into AGC Memory Items.

Capture stays inert after installation:

The equivalent flat settings are `capture.enabled=false` and
`capture.mode=off`.

```yaml
capture:
  enabled: false
  mode: off
```

The public MCP surface remains exactly `agc.read`, `agc.write`, and
`agc.admin`. Capture is exposed as actions on those tools:

| Tool | Actions |
| --- | --- |
| `agc.read` | `capture_overview`, `capture_search`, `capture_get` |
| `agc.admin` | `capture_status` |
| `agc.write` | `capture_forget` (explicit authorization only) |

## Activation sequence

Use a synthetic Memory Root first. Keep a backup and verify `capture_status`
after every transition.

1. Install Runtime 0.3.0; this still leaves Capture off.
2. Audit the active AGC route and write one content-free activation-evidence
   JSON file. It contains only schema version, route counts, hash-match facts,
   Recall Gate result, Extractor capability enum, and Hook/Scheduler/Census
   booleans—never paths, commands, source text, or user content.
3. Ask the configurator for the Runtime authorization digest, then pass that
   exact digest to the mutation:

```powershell
$status = & "$repository\scripts\configure-capture-host.ps1" `
  -Action Status -CodexHome $codexHome -MemoryRoot $memoryRoot `
  -InstallRoot $installRoot -ActivationEvidencePath $evidencePath |
  ConvertFrom-Json
& "$repository\scripts\configure-capture-host.ps1" `
  -Action EnableScanner -CodexHome $codexHome -MemoryRoot $memoryRoot `
  -InstallRoot $installRoot -ActivationEvidencePath $evidencePath `
  -ExpectedActivationDigest $status.data.activation_digest
```

   The configurator obtains this digest live from `agc-capture activation`;
   it is not a separate Host-only approximation. Re-run `Status` after any
   Runtime, configuration, evidence, Hook, Scheduler, budget, or state change.
4. Configure one canonical Codex source root and exclusions. Start with
   `scanner_only`, not `runner`.
5. Run one bounded census. The census window is exactly 7-day and has a hard
   input ceiling of 100,000 source records.
6. Review `capture_status`, `capture_overview`, and a small
   `capture_search`. Confirm the source binding, accounting, quarantine, and
   silent-loss counters before enabling background operation.
7. Enable the Hook only after its exact launcher hash passes the local latency
   report. The Hook is only a dirty hint; Scanner remains authoritative and is
   the fallback when a Hook marker is missing, late, malformed, or unavailable.
8. Enable `runner` only with an explicit positive budget, frozen Census, and
   verified Extractor/Provider capability. Provider/model work can have background cost; installation and
   scanner-only census do not promise zero cost.

Relevant configuration controls include `capture.sources`,
`capture.exclude.task_ids`, source-level `include_subagents`, `paused`, mode,
Provider selection, and Runner budget. Exclusions are applied before new
observations are accepted; they are not a provider-side deletion mechanism.

### Codex App Runtime on Windows

When Codex App is the primary Session host, bind Capture to the App-managed
Runtime and an explicit model boundary:

```yaml
capture:
  extractor:
    kind: codex_exec
    executable: codex-app
    model: gpt-5.6-sol
```

The exact `codex-app` selector searches only the bounded App Runtime location
under `%LOCALAPPDATA%\OpenAI\Codex\bin`. It never falls back to PATH, an npm
CLI, another model, the registry, or a network lookup. Missing, invalid, or
ambiguous App Runtime candidates fail closed as Extractor unavailable. This
selector is Windows-only in Runtime 0.3.0; other platforms must keep an
explicit literal executable command.

The resolved executable identity is included in backfill authorization. After
Codex App updates its Runtime, run `prepare-backfill` again and use the new
authorization digest. Existing literal executable commands remain supported
as explicit operator overrides.

The strict activation-evidence schema is:

```json
{
  "schema_version": 1,
  "effective_v2_skill_count": 1,
  "legacy_v1_skill_count": 0,
  "mcp_block_count": 1,
  "memory_root_count": 1,
  "runtime_hash_matches": true,
  "config_hash_matches": true,
  "recall_gate_passed": true,
  "extractor_capability": "ready",
  "hook_enabled": false,
  "hook_trusted": false,
  "hook_latency_passed": false,
  "scheduler_enabled": false,
  "frozen_census": false
}
```

Use `not_assessed`, `invalid`, or `unavailable` instead of `ready` when that is
the truth. Never mark a fact ready merely to obtain a digest.

## Read and classify

Start with `{"action":"capture_overview"}`. Use a narrow
`capture_search` with strict filters and a small limit, then `capture_get` for
one observation or receipt. A classification result remains Capture evidence
until an explicit, policy-valid `agc.write` operation creates or updates a
formal Memory Item.

Do not claim that every task becomes memory. Capture may discover zero, one,
or several observations, and policy can suppress or quarantine them.

## Pause, disable, and rollback

`Pause` stops new processing while preserving configuration and Capture data.
`Disable` removes owned Hook/scheduler activation and returns configuration to
off; it does not delete already captured data.

Host configuration changes use unique before-images and a transaction marker.
Use `Rollback` to restore the latest committed Host configuration transaction.
After Capture data exists, rollback means configuration rollback—not binary
downgrade and not data deletion. A binary downgrade after Capture data exists
is unsupported unless a separately verified compatibility path says otherwise.

Formal backup/restore includes managed Capture data. Keep the current Runtime
available until restored data has passed validation.

## Hard forget

Hard forget is separate from pause, disable, exclusions, and provider
retention. It requires a direct user request and the literal authorization
`explicit_user_request`:

```json
{
  "action": "capture_forget",
  "authorization": "explicit_user_request",
  "target": {
    "type": "observation",
    "observation_id": "co_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
}
```

A revision target instead supplies the exact `adapter_id`, `source_root_id`,
`task_id`, and `revision_id`. Runtime removes matching managed primary and
backup copies transactionally and leaves only the defined content-free
suppression record. It cannot promise deletion from Codex, a model Provider,
external logs, or backups outside AGC management.
