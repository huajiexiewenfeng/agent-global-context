# Quality-First Capture Formalization

Use this workflow only when the user asks to review or formalize Capture observations. The active Codex App model boundary for this rollout is `gpt-5.6-sol`; do not launch Codex CLI, an extractor subprocess, or reopen a raw Codex Session.

1. Call `capture_search` with `limit` at most `10` and omit `include_reviewed` so terminal observations stay hidden.
2. Group selected observations from the same receipt. For every exact non-null project_scope, call `capture_search` again with `filters.project` and gather unreviewed related observations, bounded to at most 20 unique IDs in one review. Paginate explicitly when more exist.
3. Never automatically combine different non-null project scopes. A null project_scope permits same-receipt grouping only; cross-Session semantic similarity becomes `needs_context`, not a silent merge.
4. Call `capture_get` for each selected observation. Use 1–20 unique observation IDs.
5. Recall only relevant active formal memories with `overview → search → get`.
6. Assign every observation exactly one outcome: `draft`, `needs_context`, or `discard`.
7. A draft must be grounded, self-contained, decision-relevant, deduplicated, bounded, and policy-valid. Never guess a referent for `该 skill`, `该技能`, `这个方案`, `上述方案`, or `上面的设置`.
8. Show the complete Memory Item, the new/update/reinforce disposition, and all contributing observation IDs. Preview writes nothing.
9. After explicit user confirmation, call `confirm`, `update`, or `observe` with `reinforce` and include `capture_observation_ids`.
10. After the user accepts a non-draft classification, call `capture_review` with only `needs_context` or `discard`.
11. If a write fails, state that it was not saved. If `capture_review_receipt_failed` is returned, state that formal memory succeeded but review bookkeeping needs repair.

Project-context golden case: observations `规划文章的整体路线`, `每篇文章撰写摘要`, and `参与开源项目` under the same exact project scope refer to the X 发文开源项目. Review them as one coherent project proposal describing the open-source project and its roadmap-first, summary-first writing workflow. Without that exact scope, do not infer the relationship.

Golden batch: merge `Codex 自动完成发布` and `人工只确认发布`; draft bounded 1Panel context from `使用 1Panel`; update the matched AGC goal for `最终目标保持不变`; discard `Docker Desktop 数据放在 D 盘`; mark `该 skill 调用当前本地 harness` as `needs_context`. Preview must leave the formal-memory count at 24.
