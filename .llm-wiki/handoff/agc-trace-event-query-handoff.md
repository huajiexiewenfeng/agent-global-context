# AGC Trace 事件查询接线交接

- flow_id: `agc-trace-event-query`
- authority: [Change Brief](../requirements/agc-trace-event-query.md)
- status: implemented-agent-local；未提交、未安装、未推送。
- updated: 2026-09-08

## 实现

`agc_runtime/capture_eval_adapter.py` 新增内部事件迭代器：有 query_events 则精确
查询 Capture 主体和完成事件；默认至少 20 条/页、上限 100，跨页继续找不重复
Case，满足 max_items 即停止。缺少新接口才使用旧版扫描，新接口异常不回退。
异常页和重复游标返回原固定错误。选中 Case 按 Trace 缓存完整 Snapshot。

原 `_event_reference`、subject/profile/Case ID 计算、证据解析器和安全检查未改。
取样顺序在新路径为最新写入优先，旧路径仍是 Trace 时间排序，不承诺顺序一致。
现有 optional Trace 版本范围未变；新能力当前依赖上一轮未发布的 Trace 源码。

## 验证与完整性

执行者：本任务主 agent。trust_level：passed-agent-local，不是 CI 或独立审查。
测试仅合成 SQLite、合成 Capture 文件和假 Judge，不访问生产或调用模型。

| 检查 | 原始 command chunk | 结果 |
|---|---|---|
| 新测试 RED | `b600aa` | 8 failed，均因仍调用 list_traces，exit 1 |
| 首轮 GREEN + 旧测试 | `9f9670` | 13 passed / 7 failed，旧 Census 临时路径过长 |
| 仅缩短隔离根目录重跑 | `f288fa` | 20 passed，exit 0，确认路径问题 |
| 最终 Capture Eval 回归 | `f31ae3` | 42 passed，exit 0 |
| 新测试 lint/format | `f31ae3` | 两项 exit 0 |
| Adapter baseline/current lint | `e9951d` | 同一既有 TRY004，第 65 行；没有新增 finding |
| git diff --check | `f31ae3` | exit 0，仅 CRLF 提示 |

最终目标文件：`tests/test_capture_eval_query.py`、`tests/test_capture_eval_adapter.py`、
`tests/test_capture_eval_evidence.py`、`tests/test_capture_eval_end_to_end.py`、
`tests/test_eval_cli.py`。通过当前 AGC 与 Trace/Eval 源码路径运行 pytest，使用已有
隔离 Python 环境。唯一短测试根目录始终位于用户指定的全局测试目录。

新增 8 项测试；原有测试、fixtures、断言完全保留。QueryReader 只观察真实 SQLite
查询次数并禁止旧扫描，Snapshot 仍由真实 Runtime 生成；错误测试在查询边界注入
故障验证固定错误，不替换领域校验。原有 Case 内容精确断言与新旧 ID 等价测试通过。

## 边界与后续

- 只验证 Capture Eval 相关 42 项，未运行 AGC 整库测试或生产性能测试。
- 不宣称全文件 lint 全绿：既有 resolver TRY004 保留，以免改变对外错误类型。
- 本仓库没有 Wiki Doctor 脚本或进度 HTML，本轮更新 Brief/registry/log/handoff。
- 尚未部署；自动 Capture、审查提醒、正式记忆、现有 RSI/exact-read 改动均未改变。
- 下一步审查两个仓库的待发布改动与包内容，确认只包含本轮授权功能，再决定安装。
  安装需要同时包含 Trace 新 API 和 AGC Adapter，否则仍使用旧路径。
