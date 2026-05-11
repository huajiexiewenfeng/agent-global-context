# Confidence Policy

## Goal

Make memory confidence interpretable and auditable.

## Recommended Values

Use four values:

- `confirmed`
- `observed`
- `inferred`
- `tentative`

## Definitions

`confirmed` means the user explicitly stated it, explicitly approved it, or asked the agent to remember it.

`observed` means it comes from reliable local evidence such as repository files, command output, configuration, or repeated visible behavior.

`inferred` means the agent derived it from context, but the user has not confirmed it and no direct source proves it.

`tentative` means it may be useful, but evidence is weak, ambiguous, or likely temporary.

## Promotion

- `tentative` can become `observed` after repeated reliable evidence.
- `inferred` can become `confirmed` only through user confirmation.
- `observed` can become `confirmed` when the user explicitly agrees.

## Guardrails

- Do not mark agent guesses as `confirmed`.
- Do not use confidence as a numeric score in the MVP.
- If a memory is sensitive and not confirmed, stage it for review instead of committing it.

