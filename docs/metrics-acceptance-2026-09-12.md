# AGC 指标原规格验收（2026-09-12）

- flow_id: agc-metrics-upgrade-v1
- 结论：部分通过；不能进入“整体完成/生产已验收”状态。
- 范围：原 P1–P4 规格核对、合成用户流程、HTML 检查。不改生产、不调用真实 Judge、不安装或推送。
- 证据级别：本地 agent 执行的合成测试与源码核对，不是独立外部审计或用户 Review。

## 需要补齐的功能

续做更新：M3 可读矩阵与实现版本比较已实现，相关 68 项合成回归通过
（fbd1e2，5.72 秒）。旧冻结批次兼容；配置/结果引用仍缺绑定来源，不声称
完全核验。下列第 1 项是发现时状态，不再代表矩阵/版本代码仍未实现。

单案例正文入口的补丁被安全审批拒绝，未落入代码：私有源正文/Judge 理由
返回 Codex 宿主响应可能被会话历史保存，需要用户明确授权这一数据去向。
尚未读取或输出真实内容；草稿红测已撤下，避免把未获准入口当已实现交付。

1. **M3 字段核验与展示不足。** `metrics_compute.py:238` 将 implementation_version、configuration_identity、result_reference 固定为 unchecked/unknown。身份、开始、终态有实际匹配，但这不能算版本/配置/结果引用已经核验。`metrics_report.py:294` 仍通过折叠 JSON 展示这些字段，未形成原规格要求的可读字段矩阵。数据确实缺失时保留 unknown 是正确行为；不能把尚未实现的核验也说成纯数据缺口。
2. **单案例证据审阅入口尚不完整。** `metrics_review_evidence.freeze_evidence` 已有受控解析能力；`metrics_cli export-review-evidence` 仅输出引用索引和无正文 HTML。页面提示“按需通过本地解析器查看”，但当前 CLI/Skill 没有对应的单案例查看操作。人工能看到标签和 case_id，不能仅凭它们判断初评是否有依据。不要以批量正文 HTML 导出来补这个缺口。

下一实现顺序：M3 最小字段矩阵/可核验字段 → 单案例按需证据查看；沿用既有来源验证和授权，不新增指标、不建监控或通用评估平台。

## 规格覆盖核对

| 项目 | 当前依据 | 本次判断 |
|---|---|---|
| P1 批次冻结、程序指标、方法说明 | metrics_models/collect/compute/report；报告及边界测试 | 已实现基础流程；历史基线生产对照本次未跑 |
| P2 独立 Capture/业务收据 | metrics_evidence/business；read/write/admin 操作入口 | 有代码及既有合成测试；不是生产覆盖证据；新增开销对照尚无本次结果 |
| M2 两步内容初评 | assessment、runner、review_batch；质量报表测试 | 有模拟验证，不代表真实 Judge 语义准确 |
| M3 Trace 可追溯性 | 独立尝试清单与根事件匹配 | 部分实现，字段核验/矩阵缺口见上 |
| M4 计划、尝试、结果状态 | eval_summary/history/review_batch | 可展示计划与未评状态，不把成功结果库当全部计划 |
| M5 研究联系双轴 | research CLI/source/plan、review_batch | 合成研究流程通过；历史背景缺失仍 unknown，不能归因 AGC 收益 |
| Judge 配置隔离与授权 | metrics_host/gateway/eval | 此次使用 fake gateway；没有验证生产模型实际身份 |
| P4 显式 Skill 与人工修订 | agc-metrics-review、review、CLI render | 合成追加反馈、原初评保留、无模型复算通过；真实用户 Review 未发生 |
| 案例下钻 | 引用索引、freeze_evidence | 缺可用的单案例正文查看入口 |
| 受管理报告/结果遗忘 | attempt lock、source bindings、forget intent、report artifacts | 上轮已验证；本轮未重做全部故障回归，不以历史结果冒充本次新跑 |
| HTML 视觉与交互 | 已生成 reviewed.html；本地浏览器导航尝试 | 未验收：浏览器安全策略阻止 file URL，未尝试绕过 |
| P5 安装与真实试点 | 无本轮安装或发送授权 | 未执行 |

## 本次实际执行

新增 `tests/test_metrics_acceptance.py`，使用已有合成研究来源和假 Judge，走通：

准备研究计划 → 模拟评估 → 受管理报告 → 引用导出 → 合成人工修订 → 两次离线 render。

断言：两份 HTML 字节相同；原始 review 文件字节不变；fake gateway 调用保持一次；离线 render 禁止 load_host；五个方法入口存在；正文与模型自由文本没有进入 HTML。反馈为测试夹具，绝不是替用户认可或修正真实记忆。

执行命令（仓库 venv，TEMP/TMP=D:/tmp_test，PYTHONDONTWRITEBYTECODE=1）：

```text
python -B -m pytest tests/test_metrics_acceptance.py tests/test_metrics_report.py tests/test_metrics_review_report.py tests/test_metrics_review.py tests/test_metrics_attempts.py tests/test_metrics_business_report.py tests/test_metrics_review_queue.py -q --tb=short -s -p no:cacheprovider --basetemp D:/tmp_test/metrics-acceptance-0912
```

- 结果：58 passed in 8.62s，退出码 0；原始工具输出 ded74c，启动输出 56bd2f。
- HTML：`D:/tmp_test/metrics-acceptance-0912/test_prepare_judge_report_feed0/reviewed.html`。
- 本轮仅增加验收测试和记录，未修改运行时代码。
- 视觉检查：Browser 明确拒绝本地 file URL，并禁止绕过；因此没有截图、布局或点击验收通过的证据。需用户在本地审阅，或后续提供获准的预览入口；本轮不通过切换表面/代理方式绕过策略。

## 交付边界

不能用本次 58 项、上轮 505 项或 HTML 文件存在来宣称原规格全部完成。先补上述功能缺口，再完成可执行范围的验收；视觉验收限制单列，不静默豁免。生产安装、真实初评及真实人工 Review 仍需分别满足权限和证据要求。
