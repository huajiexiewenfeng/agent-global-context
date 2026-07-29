---
schema_version: 2
id: agent-runtime-research
kind: interest
subkind: research_topic
lifecycle:
  status: active
confidence:
  level: confirmed
temporal:
  type: evolving
  valid_from: "2026-07-01"
  last_observed: "2026-07-28"
  review_after: "2026-10-28"
recall:
  prior: medium
  decision_impact: medium
  exposure: scoped_card
  scopes:
    - learning
    - research
  applies_when:
    - learning_plan
    - research_direction
  not_when:
    - unrelated_delivery
  freshness_policy: periodic
sensitivity: normal
provenance:
  created_at: "2026-07-01"
  updated_at: "2026-07-28"
  confirmed_at: "2026-07-28"
  evidence_refs:
    - codex-task:design-agc-v2
topic: agent-runtime
intensity: high
trend: rising
motivation: build_reusable_agent_infrastructure
---
## Memory Card

当前重点研究 AI Agent、Skill 与 Runtime

## Full Meaning

用户目前持续研究 AI Agent、Skill 和可插拔 Runtime，并希望逐步深入到 LLM 训练与基础原理。兴趣方向会变化，不能当作永久身份。

## Application Boundary

用于学习路线、研究选题和相关技术方案；与当前任务无关时不主动提及。

## Rationale

近期多个 Codex 任务中由用户明确表达。
