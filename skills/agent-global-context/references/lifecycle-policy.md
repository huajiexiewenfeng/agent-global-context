# Lifecycle Policy

## Goal

Prevent temporary context from becoming stale long-term noise.

## P4 TTL

`P4` is temporary task state. Treat it as stale when:

- the user starts a clearly different task
- the project active goal changes
- the next action is completed
- the session summary is older than the configured review window

## Active State

Update `projects/<project-id>/active.md` in place.

Do not keep many obsolete "next action" lists in `active.md`.

## Session Summaries

Session summaries may remain under `sessions/` as historical recovery points, but recall should load only recent summaries referenced by `active.md` or allowed by `config.yaml`.

## Archive

When active state is no longer current:

1. Move durable decisions to `decisions.md`.
2. Move durable engineering facts to `engineering.md`.
3. Remove completed next actions from `active.md`.
4. Leave the dated session summary as history.

## Staging in MVP

The alpha MVP may populate staging through auto capture when `auto_capture.enabled` is true.

Auto capture into staging begins when `agent-global-context-capture` exists and `auto_capture.enabled` is true.
