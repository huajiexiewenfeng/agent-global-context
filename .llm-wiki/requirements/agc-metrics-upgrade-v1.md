# AGC 指标改造：P1 只读报表

- flow_id: agc-metrics-upgrade-v1
- status: planned
- updated: 2026-09-11

## 目标与来源

承接用户已确认的指标 v1.1 和整体方案：先完成只读指标、冻结批次及离线 HTML，不将记录量当收益。本页将协作工作区同名需求的 P1 范围带入仓库。用户随后要求先提交现有代码并合并 main；指标开发停在准备阶段，尚无指标功能代码，其余阶段未实施。

## 范围与非目标

新增独立 metrics 模块、CLI、测试；只读读取明确指定的 Trace/Eval SQLite 和 Capture receipt 元数据。现有脏工作区修改保留。不改 Capture/Recall、正式记忆、Runner、生产配置，不调用 Judge，不修改 Runtime 仓库，不安装或推送。

## Acceptance

- 冻结窗口/截止、纳入清单、来源状态、口径及转换版本；同一批次重算一致。
- M1 可见 Capture cycle 开始队列状态和独立完成项事件量分开；重复、冲突、跨窗口与非法记录明确处理。
- M3 不以 Trace 自身作完整覆盖分母；receipt 当前快照只能作受限样本线索，未解析引用为 unchecked。
- M4 仅报告当前可观测 Eval 记录分布；没有计划与证据核验，不称计划覆盖或可用判断率。
- M2/M5 未执行明确展示；所有五组指标均有查看方法、来源、样本/未知状态；HTML 离线、无远程资源、无原始正文。
- SQLite 以 mode=ro + query_only 读取，不初始化数据库；render 不读取生产源或调用模型。

## 执行计划

1. tests/test_metrics_batch.py：先验证输入白名单投影、稳定批次、时区和完整性校验，再实现 metrics_models.py。
2. tests/test_metrics_compute.py：先验证状态/窗口/缺分母，再实现 metrics_compute.py。
3. tests/test_metrics_collect.py：临时 SQLite/receipt 夹具验证只读、安全字段投影及错误状态，再实现 metrics_collect.py。
4. tests/test_metrics_report.py：验证 HTML 转义、方法说明、空数据及 CLI 离线复算，再实现 metrics_report.py、metrics_cli.py 和入口。
5. 相关测试、合成报表和已存历史基线对照；生产源若无有效权限不重试或绕过，只交付合成报告并说明限制。

## External Dependencies

agent-runtime-modules 源码只读核验 events/results 表合同；当前 EventStore/EvalStore 读取会进行初始化，P1 采用本地只读 schema adapter，不调用初始化型 API。兼容范围 events v0.1 / results v0.1；不匹配显式失败，不猜 schema。

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | 用户已确认方案和 P1 执行 | 2026-09-11 |
| design | done | 本页 Acceptance | 2026-09-11 |
| plan | done | 本页执行计划 | 2026-09-11 |
| development | pending | 用户要求先合并现有代码；尚无 metrics 功能代码 | 2026-09-11 |
| testing | pending | 待执行 | 2026-09-11 |
| archive | pending | 未安装/提交/推送 | 2026-09-11 |
