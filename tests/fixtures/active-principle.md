---
schema_version: 2
id: difficult-but-correct
kind: principle
subkind: decision_standard
lifecycle:
  status: active
confidence:
  level: confirmed
temporal:
  type: durable
  valid_from: "2026-07-23"
  last_observed: "2026-07-28"
  review_after:
recall:
  prior: high
  decision_impact: high
  exposure: core_card
  scopes:
    - work
    - learning
    - research
    - architecture
  applies_when:
    - substantial_decision
  not_when:
    - trivial_task
  freshness_policy: event_driven
sensitivity: normal
provenance:
  created_at: "2026-07-23"
  updated_at: "2026-07-28"
  confirmed_at: "2026-07-23"
  evidence_refs:
    - codex-task:design-agc-v2
---
## Memory Card

做难而正确的事情

## Full Meaning

在重要工作、学习和研究决策中，优先选择长期价值更高、结构更正确的方案，不因短期省事牺牲关键质量。

## Application Boundary

用于会实质影响结果的选择；琐碎任务、低风险可逆操作不需要人为增加复杂度。

## Rationale

这是用户明确确认、反复用于方案选择的原则。
