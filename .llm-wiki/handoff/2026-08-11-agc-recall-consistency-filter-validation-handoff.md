# Handoff: agc-recall-consistency-filter-validation

## Result

The minimal AGC Recall consistency and Search filter validation improvement is integrated on `main` and deployed locally.

## Implemented

- Requests asking whether a project, repository, tool, or technology fits the user's research, learning, or long-term goals are explicit Recall candidates.
- Generic project or technology explanations remain no-Recall cases.
- Search filter names are restricted to `kind`, `scopes`, `decision_impact`, `sensitivity`, `exposure`, and `confidence`.
- Unknown filter names now return the standard schema-v2 `invalid_request` response instead of being silently ignored.
- Regression tests and the public tool contract encode both behaviors.

## Boundaries Preserved

- No memory object, event, candidate, or lifecycle state was created or changed.
- Query matching, ranking, progressive read stages, automatic capture, and Trace/Eval remain unchanged.
- The LLM still decides whether recalled context is useful and whether to apply it as `adapt`, `continue`, or `grow`.
- Unrelated factual and mechanical tasks remain quiet.

## Verification

- evidence: `.llm-wiki/verification/2026-08-11-agc-recall-consistency-filter-validation.md`
- result: merged `main` passed all 195 tests; deployed Runtime reports 22 valid memories and rejects `scope`
- trust_level: agent-local
- restart_required: yes, for the current Codex process to load the new Skill metadata and MCP executable

## Important Commit

- `b4c18d8` tighten AGC Recall and Search filters

## Next Observation

Use the existing three-day read-only review to compare semantically equivalent research-relevance tasks. Improve again only if new evidence shows missed high-value Recall or unrelated noise.
