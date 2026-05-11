# Directory Layout

Default root:

```text
~/.agent-global-context/
  config.yaml
  index.md

  user/
    profile.md
    preferences.md
    coding-style.md

  environment/
    machine.md
    agent.md

  projects/
    <project-id>/
      overview.md
      engineering.md
      decisions.md
      active.md
      sessions/

  staging/
    inbox.md
    pending-review.md
    rejected.md
```

## File Roles

- `config.yaml`: behavior configuration.
- `index.md`: recall entry point, project map, active memory pointers.
- `user/profile.md`: `P0` user background and durable identity-level context.
- `user/preferences.md`: `P1` technical, tool, and collaboration preferences.
- `user/coding-style.md`: `P2` coding habits and engineering style.
- `environment/machine.md`: local OS, shell, paths, tools, permissions.
- `environment/agent.md`: agent-specific setup, skills, plugins, operating constraints.
- `projects/<project-id>/overview.md`: project purpose, stack, architecture overview.
- `projects/<project-id>/engineering.md`: run commands, test commands, layout, known pitfalls.
- `projects/<project-id>/decisions.md`: durable project decisions and rationale.
- `projects/<project-id>/active.md`: current task state and next actions.
- `projects/<project-id>/sessions/`: dated session summaries.
- `staging/inbox.md`: candidate memories not yet committed.
- `staging/pending-review.md`: sensitive or high-impact candidates requiring user review.
- `staging/rejected.md`: rejected memories or anti-memories that should not be re-added.

