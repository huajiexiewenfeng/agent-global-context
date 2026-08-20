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
2. Configure one canonical Codex source root and exclusions. Start with
   `scanner_only`, not `runner`.
3. Run one bounded census. The census window is exactly 7-day and has a hard
   input ceiling of 100,000 source records.
4. Review `capture_status`, `capture_overview`, and a small
   `capture_search`. Confirm the source binding, accounting, quarantine, and
   silent-loss counters before enabling background operation.
5. Enable the Hook only after its exact launcher hash passes the local latency
   report. The Hook is only a dirty hint; Scanner remains authoritative and is
   the fallback when a Hook marker is missing, late, malformed, or unavailable.
6. Enable `runner` only with an explicit positive budget and verified Provider
   capability. Provider/model work can have background cost; installation and
   scanner-only census do not promise zero cost.

Relevant configuration controls include `capture.sources`,
`capture.exclude.task_ids`, source-level `include_subagents`, `paused`, mode,
Provider selection, and Runner budget. Exclusions are applied before new
observations are accepted; they are not a provider-side deletion mechanism.

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
