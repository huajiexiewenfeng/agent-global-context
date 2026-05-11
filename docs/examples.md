# Examples

## Remember a Preference

User:

```text
Remember that I prefer Markdown-first memory with only small YAML config files.
```

Expected action:

- Classify as `P1`.
- Write to `user/preferences.md`.
- Include source, confidence, and rationale.

## Continue Previous Work

User:

```text
Continue from my global context.
```

Expected action:

- Read `index.md`.
- Load `P0` recall summary.
- Identify the current project if possible.
- Load relevant `P3` project files and `P4` active state if continuation is requested.

## Compress a Session

User:

```text
Compress this session into global context.
```

Expected action:

- Write a dated session summary under the current project.
- Update `active.md`.
- Promote only durable `P0-P3` facts that meet the write policy.

