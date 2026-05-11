# Index Schema

## Goal

Make `index.md` a predictable recall entry point.

## Required Sections

```markdown
# Agent Global Context Index

## Recall Entry

## Always Read

## Read For Technical Decisions

## Read For Code Work

## Read For Environment Work

## Project Map

## Active Projects

## Maintenance Notes
```

## Recall Summary Convention

Memory files should contain:

```markdown
## Recall Summary

Short, non-sensitive summary used for default recall.
```

`Recall Summary` should be short enough to load frequently.

For `P0`, keep the summary limited to collaboration-relevant, non-sensitive information.

## Project Map Format

Use one mapping per line:

```text
<absolute-project-path> -> projects/<project-id>/
```

Windows example:

```text
C:\Users\me\Documents\agent-global-context -> projects/agent-global-context/
```

## Explicit Project Binding

User-confirmed `Project Map` entries are authoritative and should be used before Git remote or directory-name heuristics.

## Active Projects

Use `Active Projects` to point to current project state files:

```markdown
- `projects/agent-global-context/active.md`
```

