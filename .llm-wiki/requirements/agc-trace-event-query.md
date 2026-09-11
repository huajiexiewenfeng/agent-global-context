# AGC Capture Eval 使用 Trace 事件查询

- flow_id: `agc-trace-event-query`
- status: implemented-agent-local
- user_authority: 用户在 Trace query_events 本地交付后要求“继续”；当前分支开发。
- documentation_mode: new Change Brief；独立于既有 RSI 与审查读取修复。

## 范围与验收

只修改 `agc_runtime/capture_eval_adapter.py`、新增测试及对应说明。
优先使用 Trace query_events，按 AGC Capture 主体与完成事件精确查询；跨页按原
case_id 去重，达到 max_items 即停止。只为选中 Case 加载完整 Snapshot，同一
Trace 复用 Snapshot。不修改领域引用校验、Case ID 或证据解析器。

旧 Runtime 没有 query_events 时保留现有 list_traces/events 路径；新接口存在但
失败不能回退全库遍历，返回已有固定错误。分页返回异常或重复游标必须停止。
新版取样采用 Runtime 的最新写入顺序；旧路径仍按 Trace last_timestamp 排序。
不宣称新旧顺序相同；相同 subject/profile/reference 的 Case ID 不变。

不安装生产、不调用模型/Judge、不改自动 Capture/正式记忆、不提交或推送。
保留所有已有未提交改动。测试仅合成数据，临时输出在指定全局测试目录。

## External Dependencies

- project_id: agent-runtime-modules
- edge_id: none；本仓库无 cross-refs/Project Graph 注册文件，不创建推测边。
- scope: read-only
- verification_required: source
- verification_status: 当前工作树 TraceService.query_events 源码已核对，尚未发布。
- contract: keyword principal_ref/event_type/limit/cursor；EventPage.events/next_cursor。
- implementation impact: lazy import PrincipalRef；保留旧版可选 Trace 依赖能力检测。
- handoff: 后续发布时确认安装的 Trace 含新 API，当前不更改依赖版本号。

## Plan / Context Handoff

- active: Adapter 查询路径、tests/test_capture_eval_query.py 与本页。
- read-only: Trace 源码、证据 resolver、现有 tests/fixtures、RSI 与 exact-read 改动。
- excluded: 生产、配置、发布、模型调用。
- bridge: TDD inline；新测试先在旧实现上失败，再实现最小事件迭代器。
- [x] 真实 Trace SQLite 验证不调用 list_traces；跨页去重、Snapshot 缓存、max_items。
- [x] 新 API 错误/异常分页不回退；保留原有 legacy 测试与断言。
- [x] 实现事件迭代器并保留原 Case 构造与领域校验。
- [x] Adapter/证据/端到端回归及格式检查；记录原始结果和未部署边界。

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | 当前 Adapter 与 Trace query_events 源码 | 2026-09-08 |
| design | done | 沿用已确认查询接口，明确旧版兼容路径 | 2026-09-08 |
| plan | done | 本页内联 TDD 计划 | 2026-09-08 |
| development | done | 新旧查询入口适配，领域规则未改 | 2026-09-08 |
| testing | done | passed-agent-local：8 RED；42 相关回归通过；既有 lint 1 条不变 | 2026-09-08 |
| archive | done | [本地交接](../handoff/agc-trace-event-query-handoff.md)，未部署 | 2026-09-08 |
