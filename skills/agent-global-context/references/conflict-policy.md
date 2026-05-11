# Conflict Policy

## Goal

Resolve conflicts between user-level preferences, project-level constraints, and current user instructions.

## Precedence

Use this order:

1. Current explicit user instruction.
2. Safety and sensitive memory policy.
3. Project-specific `P3` constraints and decisions for the active project.
4. User coding habits `P2`.
5. User technical preferences `P1`.
6. User profile context `P0`.
7. Temporary session state `P4`.

## Project Overrides Personal Preference

Inside a project, project-specific conventions override general personal preferences.

Example:

- User generally prefers functional style.
- Active project uses OOP conventions.
- Follow the project's OOP conventions for that project.

Mention the conflict briefly if it affects the decision.

## Current Request Overrides Stored Memory

If the user's current request conflicts with stored memory, follow the current request unless it is unsafe or impossible.

If the conflict may be durable, ask whether to update or supersede the stored memory.

## Confidence Matters

Confirmed memory beats inferred memory at the same scope.

Do not let inferred global memory override confirmed project memory.

