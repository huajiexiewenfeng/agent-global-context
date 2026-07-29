# AGC Tool Contract

The Host binds the memory root. The LLM supplies only a `request` mapping and
never chooses a filesystem root.

Only three tools are public:

| Tool | Actions | Boundary |
| --- | --- | --- |
| `agc.read` | `overview`, `search`, `get`, `history`, `evidence` | Deterministic, sensitivity-filtered reads |
| `agc.write` | `observe`, `observe_batch`, `propose`, `confirm`, `update`, `supersede`, `archive`, `reject`, `forget` | Validated and policy-controlled persistence |
| `agc.admin` | `init`, `validate`, `rebuild_catalog`, `backup`, `restore`, `migrate` | Maintenance and migration |

Every request is a mapping with an `action` field plus action-specific fields.
Unknown actions and malformed fields produce a failure envelope rather than an
exception crossing the tool boundary.

Every response is a schema-v2 mapping:

```yaml
schema_version: 2
tool: agc.read | agc.write | agc.admin
action: <action>
status: accepted | deferred | rejected_policy | needs_adjudication | failed
data: {}
warnings: []
error: null | {code: <stable-code>, message: <safe-message>}
```

For Recall, start with `{"action": "overview"}` only when memory may materially
help. Narrow with `search`, fetch an explicit item with `get`, and request
`history` or `evidence` only when provenance or change over time matters.

`agc.write` receives semantic proposals chosen by the LLM. Runtime validation,
policy, deduplication, persistence, lifecycle, idempotency, backup, and recovery
remain deterministic. Sensitive content is never persisted in v2.

`agc.admin` is not a Recall shortcut. Use it only for explicit initialization,
validation, catalog repair, backup/restore, or migration work.
