# AGC Capture 人工监督改进闭环

- flow_id: `agc-capture-supervised-improvement-loop`
- status: executing
- updated: 2026-09-07
- documentation_mode: update existing Change Brief; offline implementation in progress

## 目标与已确认方向

用户确认：先在 AGC 内验证 RSI 方向的闭环，再根据复用需求提炼 Agent Runtime 通用能力。首期完成两轮人工监督改进；第二轮必须使用第一轮的证据和经验。不要求每轮都提升，不把闭环跑通宣称为完整 RSI。

首个能力：Capture 内容质量。减少一次性任务被误判为长期用户信息，同时避免丢失真实的稳定偏好、长期目标和其他耐久信号。保留有用的短期项目观察本身不是错误；应评价其内容、作用域和类别，而不是强制全部丢弃。不调整生产 Capture 覆盖率和调度。

## Sources

- 当前任务中用户确认的方向与两轮验收边界；本页为确认内容的项目摘要，不复制历史会话。
- [既有 Eval Pilot](agc-capture-eval-pilot.md) 与 [历史工作上下文](../working-context/agc-capture-eval-pilot.md)：仅作为已有集成线索，不沿用旧完成状态。
- `agc_runtime/capture_eval_adapter.py`：已有 Capture EvidenceResolver、EvalCase 生成。
- `agc_runtime/eval_profiles/agc-capture-quality.v1.json`：已有 faithfulness、durability、noise_control、atomicity、classification 五维规则。
- `agc_runtime/capture_extractor.py`：已有 ExtractorDescriptor 和版本字段。
- WikiSkill: https://arxiv.org/html/2608.27454v1 。借鉴经验、知识、技能分离和保留拒绝记录，不复制全部轨迹、不假设论文已证明生产 RSI。

## 范围

- 当前写入范围：用户已确认规格并授权实施计划与离线测试开发；本轮仅交付离线骨架，不调用真实模型。
- 候选实施范围：AGC 内一个薄的离线实验 Harness、合成样本、逐项对比报告、独立改进知识域；复用现有适配器。
- 每轮只改一个明确的提取 Prompt/规则；固定模型配置、Schema、评估规则、样本版本。若诊断表明问题在 Capsule 或其他模块，记录并停止该轮，不暗中扩大修改面。
- 只读参考：现有 Trace、Eval、LLM Wiki 公共能力。三个 Runtime 不互相新增强依赖，不修改其仓库。
- 排除：生产 Runner、正式记忆、自动晋升、扫描/锁性能修复、Recall 优化、新模型、自修改评估标准、Dashboard、通用 RSI Runtime、GitHub 推送。

## 最小流程

1. 冻结样本分组和评分规则，运行基线。
2. 根据开发集实际输出及错误形成有证据的经验记录。
3. 每轮提出一个候选 diff，说明假设、适用条件、反例、预期收益。
4. 在隔离环境重新执行基线与候选，用相同条件做逐项对比；不能只让 Judge 阅读规则后打分。
5. 形成 accept-candidate / reject / inconclusive 建议。实验接受不是生产发布。
6. 记录结果和拒绝原因。第二轮显式引用第一轮经验，说明继续、修正或放弃了什么。
7. 两轮结束后使用未向改进者开放的最终验收集。发布需要用户另行确认；若不发布，也可验收闭环机制。

## 样本方案（待确认，不是已生成数据）

先拟定 24 条合成、安全的 Capsule 场景，不读取或导出生产 Session。每组 4 条：2 条开发、1 条验证、1 条最终验收；合计 12/6/6。分组按独立任务族，不把同一信号的改写/连续 revision 分散到不同集合。

| 场景组 | 必须区分的边界 |
|---|---|
| 稳定偏好 | 持续协作偏好与本次临时要求 |
| 持续目标/项目 | 多次明确的长期目标与一次性执行状态 |
| 一次性命令 | 当前操作要求不能扩大成长期偏好 |
| 临时状态/故障 | 当前故障不能变成长期能力或兴趣断言 |
| 混合信号 | 同一输入中保留耐久信息，不连带长期化临时信息 |
| 歧义/修订/转述 | 不把他人的话归给用户，不把上下文不足当作确定事实 |

开发集示意（全部虚构，不是用户记忆）：

- D01：「今后代码评审请先说高风险问题，再给建议。」应保留协作偏好。
- D02：「这次评审先看缓存模块。」不推断长期缓存兴趣；至多作为短期任务证据。
- D03：「未来半年我每周研究一次数据库执行计划；现在先重启服务。」保留研究目标，不把重启操作长期化。
- D04：「同事说他喜欢 Go，我还没决定用什么语言。」不生成用户喜欢 Go 的结论。

每例标注 required_claims、forbidden_claims、允许的短期/项目结果、允许的不确定性和判定理由。独立标注并冻结后再运行基线，不能根据候选输出改答案。具体最终验收题和答案不能进入候选生成上下文；需要独立评估执行边界。若同一任务的改进者已读过，则将该样本降为开发样本，不再声称盲测。

24 条仅用于机制验证，不代表生产质量的统计充分性。未来加入历史数据前单独审查安全 Capsule、访问范围和模型发送授权。

## 评估与建议接受规则（待确认）

- 主指标分开报告：错误长期化数量、应保留耐久命题的遗漏数量、无依据断言数量。分母为各自适用的命题/样本数，不混成一个模糊满分。
- 同时报告 schema/执行错误、分类错误、人工与 Judge 分歧、延迟和实际可用 token usage；未知用量不记为零。
- 复用现有五维 Profile 作为辅助证据。其 durability 规则对正确 zero/短期结果的适用性须先校准；必要时在基线前建立独立版本的实验 Profile，两轮内冻结，不覆盖生产 v1。
- 有争议的语义匹配由人工复核；不以完全字符串相等替代语义正确性，不以 Judge 自评作为唯一真值。
- 建议接受候选至少需要：目标错误在验证集严格减少、耐久命题遗漏不增加、无新增无依据断言、无新增执行/Schema 错误。报告逐项改善和退化，不仅均分。
- 首次差异可能是随机波动：对预定验证集合按相同条件复跑基线和候选；方向不稳定则 inconclusive。样本太小或缺少目标错误时，补充开发证据，不能宣称有效提升。
- 第二轮和最终验收同时对比当前已接受基线与初始基线，避免累计退化。验收集不用于继续调参；查看后它不再是后续未见样本。

## 经验记录与可追溯性

改进知识与 AGC 用户正式记忆隔离。先用现有 LLM Wiki 的记录/来源机制；由 AGC 定义内容，Runtime 负责确定性读写。仅保存安全抽象和受控引用，生产私有内容不进入 Git。

一条经验记录包含：问题、条件、支持/反例引用、假设状态（provisional/supported/refuted/superseded）、候选 diff 引用、评估结果引用、接受/拒绝理由。拒绝技能修改不删除实验历史，错误知识可以被反驳或替代。

实验记录关联 experiment_id、round_id、case_id、baseline/candidate hash、AGC/模型配置/Prompt/Schema/Profile 版本、样本集 digest、Trace 引用、Eval 结果引用和人工决定。执行事实、评估结果、经验解释分别归属 Trace、Eval 和领域知识记录。

## External Dependencies

- agent-runtime-modules：已有通用 Trace/Eval；本轮仅参考，不扩展公共协议。上轮只读 review 复现了 Eval 接受 Case 外证据引用的问题。真实模型评分前，必须验证引用约束；可在 AGC 实验边界增加本地强校验并记录通用修复 handoff，不能将已知不可信结果视为验收通过。
- llm-wiki-runtime：候选知识存储依赖。接口与隔离 profile 的接入仍待 source-verified；当前不声称已接通，不做迁移或更改其仓库。
- 两项 dependency verification_status: draft；derived_staleness: unknown；本页是规格草案，不是已就绪的实施合同。

## 验收

- AC1：样本、版本和规则冻结；开发/验证/最终验收访问边界有记录。
- AC2：基线和每轮候选实际执行，结果可逐项回溯到安全输入、版本及证据。
- AC3：共两轮；第二轮引用第一轮经验并解释它如何影响本轮提案或决定，不机械重试同一失败方案。
- AC4：接受、拒绝或证据不足都有明确结果，失败尝试保留，重跑不重复写入决定。
- AC5：最终报告分开说明机制验收与质量收益；允许机制通过、收益未证实。
- AC6：无正式记忆写入、无生产配置/Runner 更改、无自动发布；测试产物仅放用户指定的统一测试目录，版本控制内仅保存安全合成资料和规格。

## Plan

- active_plan: ../working-context/agc-capture-supervised-improvement-loop-plan.md
- status: confirmed
- next_gate: 离线测试与代码审查；真实样本及模型实验另行授权。

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | 当前用户已确认 AGC 优先、两轮人工监督方向 | 2026-09-05 |
| design | done | 用户“可以 继续”确认规格；真实盲测题未生成 | 2026-09-05 |
| plan | done | 已记录分阶段实施计划；本轮仅离线骨架 | 2026-09-05 |
| development | active | 离线开发已授权，生产与模型实验排除 | 2026-09-05 |
| testing | active | 最新版本指纹、离线核心与 provider 回归 64 passed；此前全量 1453 passed；真实模型及语义验收未做 | 2026-09-07 |
| archive | pending | 尚未完成闭环 | 2026-09-05 |

## Routing

- intent: 执行用户确认后的实施计划和离线测试开发。
- primary_stage: project-develop / execution-handoff
- secondary_bridges: writing-plans, test-driven-development, verification-before-completion
- confidence: high
- reason: 新的可独立验收交付，不覆盖既有 Eval Pilot。
- next_gate: integration-boundary-review; real-model-authorization-before-experiments
- routed_at: 2026-09-07
