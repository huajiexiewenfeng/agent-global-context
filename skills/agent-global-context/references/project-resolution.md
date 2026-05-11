# Project Resolution Policy

## Goal

Map the current task to a stable project context directory.

Project memory lives under:

```text
projects/<project-id>/
```

## Resolution Order

1. Use any explicit project binding confirmed by the user.
2. Use `index.md` `Project Map` if the current working directory or user-provided path matches an entry.
3. If inside a Git repository, derive a candidate from the Git remote repository slug.
4. If no Git remote is available, derive a candidate from the current directory name.
5. If the project id is new or ambiguous, ask the user before creating project memory.

User-confirmed bindings are authoritative. Git remote and directory-name slugs are only heuristics.

## Slug Rules

Use lowercase ASCII slugs:

- Convert spaces and underscores to hyphens.
- Remove characters other than letters, numbers, and hyphens.
- Collapse repeated hyphens.
- Trim leading and trailing hyphens.

Examples:

```text
C:\Users\me\Documents\New Project 2 -> new-project-2
git@github.com:owner/Agent Global Context.git -> agent-global-context
```

## Index Entry

When a project id is confirmed, add it to `index.md`:

```text
<absolute-project-path> -> projects/<project-id>/
```

## Guardrails

- Do not create project memory for a random temporary directory without confirmation.
- Do not merge unrelated projects into the same project id.
- If two paths map to the same project intentionally, record both paths in `index.md`.
