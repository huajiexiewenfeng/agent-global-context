# Codex App Runtime Extractor Design

## Goal

Make Codex App the preferred model runtime for this AGC deployment so Capture can use the same authentication, model availability, and runtime version as the user's primary Codex App workflow. The immediate acceptance target is a successful AGC capability preparation and historical Session extraction with `gpt-5.6-sol`.

## Current Problem

The Capture configuration accepts a static executable command. On this Windows host, PATH resolves `codex` to an npm-installed CLI `0.142.0`, while Codex App runs its own Runtime `0.149.0-alpha.4` under `%LOCALAPPDATA%\OpenAI\Codex\bin\<version-id>\codex.exe`. The old CLI rejects `gpt-5.6-sol`, even though the App Runtime successfully invokes it.

Hard-coding the current App Runtime version directory fixes one run but breaks when Codex App updates. Falling back silently to PATH could also change the runtime or model boundary without user awareness.

## Configuration Contract

`capture.extractor.executable` gains one reserved selector:

```yaml
capture:
  extractor:
    kind: codex_exec
    executable: codex-app
    model: gpt-5.6-sol
```

All existing literal executable commands remain supported. Only the exact single token `codex-app` activates App Runtime discovery; strings containing additional arguments continue through the existing literal command parser.

The repository defaults remain platform-neutral. The local production and Pilot configurations are explicitly switched to `codex-app` and `gpt-5.6-sol` after the installed Runtime passes verification.

## Runtime Discovery

On Windows, the resolver:

1. Reads `LOCALAPPDATA` and requires an absolute existing directory.
2. Constructs the fixed root `%LOCALAPPDATA%\OpenAI\Codex\bin`.
3. Resolves the root and verifies it remains below the resolved `LOCALAPPDATA` directory.
4. Enumerates only direct children matching `*\codex.exe`.
5. Accepts candidates only when the version directory and executable are ordinary, non-symlink paths whose resolved targets remain below the fixed root.
6. Requires exactly one valid candidate and returns it as a one-element argv tuple.

No recursive broad search, registry scan, WindowsApps traversal, PATH lookup, npm fallback, or network access is allowed. Zero or multiple valid candidates fail closed with a content-safe `capture_extractor_unavailable` result. An operator can still use a literal executable path as an explicit override.

Non-Windows hosts fail closed for `codex-app` in this phase; their existing literal executable behavior remains unchanged.

## Extraction Boundary

After discovery, the existing `CodexExtractor` remains authoritative. It still verifies:

- executable version and required `exec` flags;
- `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, and `--skip-git-repo-check`;
- read-only sandboxing and static Structured Outputs schema;
- explicit model and provider boundaries;
- bounded stdin, stdout, stderr, timeout, empty working directory, and sanitized errors.

The App Runtime usage event adds `cache_write_input_tokens`. The parser accepts the exact five-field App Runtime usage shape, validates every token field as a nonnegative integer, and continues accounting `total_tokens` as `input_tokens + output_tokens`. Unknown fields remain rejected by returning usage unavailable rather than weakening event validation.

## Data Flow

```text
Memory config (`codex-app`, `gpt-5.6-sol`)
  -> bounded App Runtime resolver
  -> exact absolute codex.exe argv
  -> existing capability probe
  -> authorization digest binds executable identity + model/provider
  -> bounded historical Session extraction
  -> observation policy/filtering
  -> isolated or production Capture store
```

The resolved executable identity remains part of the authorization digest. A Codex App update therefore invalidates prior backfill authorization and requires a new `prepare-backfill`, preventing a runtime change from being silently reused.

## Failure Behavior

- Missing/invalid `LOCALAPPDATA`: extractor unavailable.
- Missing App Runtime: extractor unavailable.
- Multiple valid `codex.exe` candidates: extractor unavailable; use an explicit literal override until the App installation is repaired or cleaned.
- Symlink, junction escape, or non-file candidate: ignored; if no single valid candidate remains, extractor unavailable.
- Unsupported App Runtime protocol or model: existing capability probe fails closed.
- No fallback to npm CLI or another model.

No diagnostic response exposes the discovered absolute executable path, Session content, authentication material, or raw model output.

## Verification

Automated tests cover:

- exact `codex-app` selector and unchanged literal command parsing;
- one valid synthetic App Runtime candidate;
- missing `LOCALAPPDATA`, missing candidate, multiple candidates, symlink/escape, and non-Windows behavior;
- App Runtime five-field usage acceptance and invalid negative/type cases;
- existing Extractor and Capture backfill/Runner/CLI regression suites.

Live acceptance on this host requires:

1. Source and installed Runtime `prepare-backfill` report `model_boundary: gpt-5.6-sol` and provider `openai`.
2. At least one representative historical Session is processed through the App Runtime without protocol failure.
3. Capture reports zero silent loss.
4. The production formal-memory count remains unchanged until observations are explicitly reviewed and promoted.
5. Test artifacts remain under `D:\tmp_test`.

## Scope

In scope: App Runtime discovery, selector parsing, App usage compatibility, configuration switch, tests, installation, and isolated live verification.

Out of scope: direct private IPC into the desktop process, automatic observation promotion, Hook/Runner activation, Codex App installation or update management, npm CLI removal, and non-Windows App Runtime discovery.
