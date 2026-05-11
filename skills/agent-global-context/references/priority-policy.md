# Priority Policy

## P0: User Background

Use for durable personal or identity-level context that affects collaboration.

Examples:

- Preferred language.
- Durable work goals.
- Explicitly shared professional background.
- Stable collaboration needs.

Default recall: summary for substantial sessions.

## P1: Technical Preferences

Use for technical and workflow preferences.

Examples:

- Markdown-first vs database-first.
- Preference for discussing design before implementation.
- Toolchain preferences.
- Architecture style preferences.

Default recall: technical decisions, planning, tool choice, architecture.

## P2: Coding Habits

Use for implementation, testing, review, and style habits.

Examples:

- Testing expectations.
- Encoding safety rules.
- Code review preferences.
- Branching and commit habits.

Default recall: code writing, debugging, refactoring, review.

## P3: Project and Environment

Use for project facts and machine/workspace facts.

Examples:

- Project paths and mappings.
- Build and test commands.
- Dependencies and known pitfalls.
- Architecture decisions.

Default recall: when cwd or request maps to a project.

## P4: Temporary Session State

Use for current task state.

Examples:

- What was done in the last session.
- Next actions.
- Blockers.
- Unfinished implementation notes.

Default recall: only continuation requests.

