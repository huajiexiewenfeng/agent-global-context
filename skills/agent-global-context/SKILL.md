---
name: agent-global-context
description: Use when a task may benefit from personal long-term memory, the user requests durable recall or storage, or AGC maintenance is requested.
---

# Agent Global Context

AGC provides optional personal long-term memory. This capability description
contains no personal facts; memory enters context only through an explicit tool
read.

## Decide

The LLM decides whether memory can materially improve the current result, what
to recall, and whether recalled memory applies. Small or self-contained tasks
do not call `agc.read`. Current instructions and current facts always outrank
memory.

## Recall and Apply

Read only as far as useful: `overview → search → get → history/evidence`.
Apply recalled memory as exactly one mode:

- `adapt`: silently tailor presentation or collaboration.
- `continue`: resume relevant prior work without treating stale state as fact.
- `grow`: offer at most one strongly supported, guarded growth suggestion.

The LLM owns semantic relevance, `disposition`, and `match_memory_id`; the
Runtime owns deterministic validation, persistence, lifecycle, and recovery.

## Write, Admin, and Failure

Explicit durable non-sensitive changes may call `agc.write`. Sensitive
persistence stays disabled. `agc.admin` is for maintenance and migration, not
ordinary Recall.

If `agc.read` fails, continue the main task without memory. A failed write is
not saved and must not be reported as saved. Runtime failure must not block an
otherwise-completable main task.

## References

- [Tool contract](references/tool-contract.md)
- [Application policy](references/application-policy.md)
