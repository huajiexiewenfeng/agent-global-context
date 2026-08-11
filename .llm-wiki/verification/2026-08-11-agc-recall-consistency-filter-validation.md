# Verification: agc-recall-consistency-filter-validation

## Provenance

- executor: agent-local
- date: 2026-08-11
- authority: agent-local
- implementation_commit: `b4c18d8`
- local_runtime: `080b414f62c67733b2533ccd6ff1dcc02b39185a136b30054b705e2cbd81ec73`
- exit_code: 0

## Release Gate

```text
focused Runtime and Skill suites
20 passed

feature-branch complete suite
195 passed in 237.31s

merged-main complete suite
195 passed in 230.87s

Skill validator under explicit UTF-8 process encoding
Skill is valid!

strict UTF-8/no-BOM scan
all 9 implementation files passed

git diff --check
exit 0
```

## Deployed Runtime Checks

```text
agc-mcp --version
0.2.0

agc.admin validate
status=accepted, code=valid, invalid_count=0

agc.read overview
status=accepted, memory_count=22

agc.read search with filters.scope
status=failed, error.code=invalid_request,
error.message="unsupported search filter: scope"

repository Skill SHA-256 == active Skill SHA-256
66DB6748349D4820B2383FDCC958573D01C9AAAF1634D288A370E6F7153663D0
```

## Test Integrity

- production_changes: yes
- test_changes: yes
- assertions_added_or_removed: assertions added for the Recall trigger, allowed filter recipe, contract wording, and Runtime rejection
- expected_behavior_changed: research-relevance requests are explicit Recall candidates; unknown Search filter names fail closed
- memory_mutation: none
- over_mocking_risk: low; Runtime behavior was exercised against real temporary memory stores and again through the installed CLI

## Residual Risk

- The active Codex process keeps the previous MCP process and Skill metadata until a new task or restart.
- Recall activation remains an LLM routing decision; the new wording reduces the observed inconsistency but does not make every paraphrase deterministic.
- The installer depends on a working Python command; this machine's Windows Store alias returned exit code 9009, so deployment explicitly used the repository's verified Python.
