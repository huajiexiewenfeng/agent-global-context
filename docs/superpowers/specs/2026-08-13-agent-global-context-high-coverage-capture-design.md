# Agent Global Context Codex Task Revision 可证明采集 MVP 设计

> 日期：2026-08-13
> 状态：目标已确认；Phase 1 书面规格待用户复核
> Change Brief：`.llm-wiki/requirements/agc-capture-coverage-mvp.md`
> 范围：统一 v2 路由、关闭 Recall 合同缺口，并交付不阻塞主任务的 Capture Receipt + Collected Observation 闭环

## 1. Phase 1 决策

AGC 的长期目标不是保存尽可能多的对话，而是：

> **持续理解一个正在变化的人，在不过度打扰、不越界、不制造噪声的前提下，让未来协作更连续、更准确，并支持真实成长。**

当前阻塞这个目标的不是 Recall 权重，而是 AGC 无法证明某个 Codex 任务是否真正经过了记忆检查。系统无法区分：

- 任务没有持久信号；
- Capture 根本没有运行；
- Capture 运行后失败、被延后或因来源异常被隔离。

因此，本阶段的唯一目标是：

> **在不阻塞、不改变 Codex 主任务结果且受前台延迟门禁约束的前提下，对范围内每个 Codex 主任务的已完成 Revision 进行旁路检查；每个 Revision 都产生真实、可重试、可审计的 Capture Receipt，并产生 0–8 条安全、分类明确、带来源的 Collected Observation。系统不得静默漏采、重复采集，或把 Observation 直接当成正式记忆。**

“高覆盖”指检查覆盖，不指 Observation 数量。一个正确完成、结果为 0 条 Observation 的检查，与一个产生 8 条 Observation 的检查同样有效。

### 1.1 阶段边界

| 阶段 | 交付 | 本次状态 |
|---|---|---|
| Activation Gate | 唯一 v2 Skill/MCP/Memory Root 路由；普通 Recall 生命周期与响应预算正确 | Phase 1 上线前必须完成 |
| Phase 1 — Capture Coverage MVP | Source Adapter、Receipt、Observation、Runner、Scanner、只读查看、备份/恢复/Hard Forget | 本规格范围 |
| Phase 2 — Consolidation | 跨 Revision 去重、聚合、Candidate 队列、裁决与 Formal Memory 晋升 | 明确延期 |
| Phase 3 — Application Learning | 记录记忆是否被采用、效果评估、Trace/Eval/Loop | 明确延期 |

Phase 1 严格停止在 `Capture Receipt + Collected Observation`。它不得调用现有正式记忆写入流程生成 Candidate、Formal Memory 或正式记忆 Event，也不得自动 reinforce、update、supersede 或 archive 任何正式记忆。

### 1.2 Definition of Done

Phase 1 完成时，系统必须能诚实回答：

1. 哪些范围内的 Revision 已被发现？
2. 哪些已成功检查，哪些仍在排队、延后、失败或隔离？
3. 每个成功检查的 Revision 采集了什么，为什么是 0–8 条？
4. 这些数据是否完全没有进入普通 Recall？
5. 失败、重放、崩溃、来源移动和 Capture 关闭后，状态是否仍然真实？

正式记忆数量、Observation 产出率和 Capture 调用次数都不是本阶段成功指标。

## 2. 术语与全局范围

### 2.1 Active Codex Profile 与 Source Root

- Capture 绑定一个明确配置的 Codex Profile。
- 默认 Source Root 是该 Profile 当前解析后的 `CODEX_HOME`。
- `source_root_id` 是规范化 Source Root 的不透明稳定摘要；共享仓库文档和 Capture 持久对象不保存工作站绝对路径。
- Scanner 只枚举该 Root 的活动任务与已归档任务来源；备份、恢复目录、临时副本、数据库副本和其他 Codex Profile 默认不在范围内。
- 其他 Codex Profile 必须显式加入配置，不能被“全局”一词隐式纳入。

### 2.2 “全局”的准确含义

启用 Capture 后，“全局生效”表示：

- 对已配置 Active Profile 中所有 eligible 主任务生效；
- 对该主任务今后每个成功完成的 Revision 生效；
- 不要求用户在每个项目或任务中重复开启。

它不表示：

- Windows 上所有用户和所有 Codex Profile；
- 其他恢复目录或历史备份；
- 子代理任务；
- 首次窗口之前的全部历史；
- 每个任务都必须生成 Observation、Candidate、正式记忆或 Prompt 注入。

### 2.3 Task 与 Revision

规范 Task Key 为：

```text
(adapter_id, source_root_id, task_id)
```

- Hook 路径中的 `task_id` 使用 Codex 提供的 `session_id`。
- Scanner 优先使用任务来源元数据中的 `session_id`。
- 旧来源缺少 `session_id` 时，可以退化为来源锚点 `id`，但必须记录 `identity_quality=legacy_rollout_id`，不得把文件名、`id` 和 `session_id` 静默混同。

规范 Revision Key 为：

```text
(adapter_id, source_root_id, task_id, revision_id)
```

- `revision_id` 使用成功完成回合的 `turn_id`。
- Scanner 只有看到与该 `turn_id` 匹配的完成记录，才把它判定为可采集 Revision。
- `task_started`、`turn_context`、中止回合、文件尾、文件修改时间和最后一条消息都不能证明 Revision 已完成。
- 同一 Task 后续继续对话并产生新的已完成 `turn_id`，就是新的 Revision。
- 同一 Revision 重复触发 Hook 或从活动目录移动到 Archive，不产生新 Revision。

Codex 本地 transcript 格式不是稳定公共接口。`task_complete` 是 Phase 1 Source Adapter 对当前格式的版本化解析规则，不被当成永久 Host 合同；未知身份或完成形态必须隔离，不能猜测。

### 2.4 范围状态

- **discoverable**：Source Adapter 可以枚举并建立规范身份。
- **settled**：主任务 Revision 已出现可验证的完成记录。
- **census revision**：settled、位于本次时间范围内，并在策略判定前进入覆盖分母的主任务 Revision。
- **eligible**：Census 中未被 excluded 或 coalesced 的 Revision；它们构成成功检查的分母。
- **excluded**：命中用户配置的 task/project 排除规则；只生成无正文元数据状态。
- **coalesced**：多个已配置来源指向同一可验证 Revision 副本；只由一个规范 Receipt 处理。
- **subagent**：独立子代理执行；Phase 1 不作为独立采集单元。
- **unknown**：无法可靠判断主任务、子代理或完成身份；不猜成 eligible。若仍能建立 Task/Revision Key，则创建 quarantined Receipt；若连稳定 Key 都无法建立，则创建 adapter-level Source Quarantine 诊断，并把 Source Health 标为 degraded。

首次回填冻结半开窗口：

```text
[run_started_at - 7 days, run_started_at)
```

窗口端点使用 UTC 持久化，并在查看层按用户时区展示。`run_started_at` 之后的已完成 Revision 进入持续增量范围，不扩展首次历史窗口。

## 3. 架构与前台边界

### 3.1 数据流

```text
Codex Stop notification ──异步──> Dirty Marker
                                  │
活动与归档来源 ──Scanner──────────┤
                                  ▼
                         Revision Census / Ledger
                                  │
                                  ▼
                              Background Queue
                                  │
                                  ▼
                        Source Adapter + Task Capsule
                                  │
                                  ▼
                         Semantic Extractor (0–8)
                                  │
                                  ▼
                     Safety + Schema + Relevance Gate
                                  │
                                  ▼
                 Atomic Commit: Observations + Receipt
                                  │
                                  ▼
                      Explicit Capture Read Views only
```

### 3.2 Hook 只做唤醒优化

Phase 1 可以安装异步 `Stop` Hook，但 Hook 不是覆盖正确性的唯一来源。

Hook 只允许：

1. 校验公共元数据；
2. 将最小 Dirty Marker 原子 append/upsert 到本地队列；
3. 立即以成功状态退出且不输出正文。

Dirty Marker 只含：

- schema、adapter 与 source root 版本；
- `task_id=session_id`；
- `revision_id=turn_id`；
- 已校验、仍位于当前 Source Root 内的相对不透明 transcript locator，或 `null`；
- `observed_at` 与 `hook_event=Stop`。

Hook 禁止：

- 读取完整 transcript；
- 保存 `last_assistant_message`、用户 Prompt 或模型输出；
- 构建 Task Capsule；
- 调用模型、网络或 AGC 正式记忆写入；
- 做分类、去重、聚合或敏感内容持久化。

不使用 `SessionEnd` 执行语义采集。它只能作为诊断信号，不能承担完成判定、回填或重试，因为关闭/归档时机与每个完成回合并不等价，且同步执行会增加退出延迟。

### 3.3 Scanner 是覆盖权威

Scanner 负责：

- 枚举 Source Root 下的活动与 Archive 任务来源；
- 排除子代理、备份、临时副本和未知来源；
- 将每个已完成主任务 Revision 与 Receipt Ledger 做集合对账；
- 补偿 Hook 未安装、重复、延迟、取消或进程退出导致的 Dirty Marker 丢失；
- 重新检查迟到记录、活动文件移动和尾部半写状态。

`session_index` 只能补充标题或更新时间，不能证明完成或覆盖；时间戳、mtime、文件大小与字节 offset 都只能作为扫描优化。

### 3.4 Runner 承担所有重工作

Background Runner 执行来源读取、Capsule 构建、模型提取、安全检查和事务提交。默认并发数为 1。Capture 的模型不可用、来源损坏、预算不足、队列积压或 Runner 崩溃不得：

- 改变原 Codex 任务结果；
- 让原任务重试；
- 阻塞最终答案；
- 把失败冒充为成功检查。

前台 Hook 新增延迟的门禁是 `p95 < 100 ms`。若目标 Host/进程组合无法达到该门禁，关闭 Hook，系统退化为 Scanner-only；不得通过在前台少做错误检查来“通过”门禁。

旁路不等于零资源成本。Scanner 会消耗少量磁盘 I/O，Runner 会消耗 CPU、内存、网络和模型额度，可能通过资源竞争间接影响正在运行的任务。因此 Runner 必须保持单并发、可暂停，后台进程在 Host 支持时使用低优先级，并分别报告扫描读取量、运行时间、模型调用与峰值资源。Shadow Rollout 必须比较 Capture 关闭、Scanner-only 和 Runner 工作三种状态；若出现可感知竞争，优先延后 Runner 或暂停 Capture，而不是侵占前台任务资源。

## 4. Source Adapter 合同

### 4.1 最小接口

```text
describe() -> AdapterDescriptor
accept_stop(StopHookEnvelope) -> DirtyMarker
discover(ScanHint, TimeWindow) -> DiscoveryBatch
probe(RevisionRef) -> SourceProbe
load_capsule(RevisionRef, CapturePolicy) -> CapsuleResult
```

- `describe` 返回 adapter id/version、source schema version、source root id 和能力。
- `accept_stop` 只产生元数据 Dirty Marker。
- `discover` 返回 RevisionRef、下一次 opaque scan hint 和诊断，不承诺 hint 是正确性水位。
- `probe` 返回 main/subagent/unknown 与 complete/partial/aborted/unreadable。
- `load_capsule` 只加载目标 completed turn，返回内存 Capsule 与摘要，不返回整段会话。

RevisionRef 至少包含：

- `task_id`、`revision_id`；
- `rollout_anchor_id`；
- `completed_at`；
- 不含正文的 opaque locator；
- `identity_quality`；
- adapter/source schema version。

### 4.2 Scanner 适配规则

- 默认只扫描当前 Source Root 的 `sessions` 与 `archived_sessions` 来源。
- 一个来源文件可以包含多个 Revision；不得把“一个文件”当成“一个 Revision”。
- 活动文件可能被锁定或只写入半行。未得到完整完成记录时保持 retryable，不猜测完成。
- Archive 移动不改变 Task/Revision 身份。
- 来源声明为子代理时排除；来源形态未知时 quarantine。
- Source Adapter 必须宽松忽略未知非关键记录、严格验证身份与完成记录，并把 parser/schema version 写入 Receipt。

### 4.3 两种摘要

Receipt 分开保存：

- `source_fingerprint`：目标 completed turn 经 Pre-Capsule 安全清理后的规范化允许记录 SHA-256，用于副本与来源变化检查；被清理的 secret/sensitive/禁止内容不参与持久摘要；
- `capsule_hash`：隐私过滤后、实际交给 Extractor 的规范 Task Capsule SHA-256，用于重放诊断。

两者都在内存中生成并记录各自的 hash schema version，不包含路径、mtime 或整个会话。只有在相同 hash schema version 下，同一 Revision 的 fingerprint 不一致才算来源冲突；adapter/hash schema 升级不得被误判为篡改，也不会自动重跑已经 complete 的 Revision。安全清理导致 fingerprint 无法比较被移除内容的变化是有意取舍：隐私边界高于对禁止内容的变更检测。

摘要不是 Revision 身份，也不能替代 Task/Revision Key。Hard Forget 后，相关内容派生摘要必须从 Receipt、索引、缓存、备份和 Tombstone 中删除。

## 5. Revision Census、Ledger 与 Watermark

### 5.1 Census 是覆盖分母

首次回填先冻结时间窗口，再持久化仅含 RevisionRef 元数据的 Census。只有 Census 固定后，Runner 才开始消耗模型预算。

持续增量时，每次 Scanner 对账都会把新 Revision 原子登记到 durable Revision Ledger，并创建或确认 `discovered` Receipt。以下差集必须始终可见：

```text
Census/Ledger Revision Keys - Receipt Revision Keys
```

该差集就是 silent loss，正常状态必须为 0。

### 5.2 Cursor 只是优化

每个 `(adapter_id, source_root_id)` 可以保存版本化 opaque cursor、文件扫描提示、adapter version、上次扫描时间和回看边界，但：

- cursor 不删除 Ledger 中的未解决项；
- Scanner 每轮先消耗 Dirty Marker，再枚举活动与 Archive 来源；
- Scanner 必须做重叠对账，容忍乱序、迟到写入、文件移动和重复索引记录；
- 文件变短、来源锚点变化或解析异常时，从安全边界重建该文件索引；
- 只有 Census 中每个 Revision 至少有真实 Receipt 状态后，扫描 hint 才能前进。

Observation、终态 Receipt 提交成功后，Runner 才把 Revision 标记为 processed。Cursor 前进不能把未完成的 queued/retryable/deferred Revision 从 Ledger 中移除。

### 5.3 Coalescing

活动来源移动到 Archive 通常是相同 Capture Key 的 exact replay，不创建第二个 Receipt。

只有多个显式配置的 Source Root 确实指向相同 Revision 且 fingerprint 一致时，非规范副本才可记录 `coalesced_to`。身份或 fingerprint 不能证明一致时不得静默合并。

## 6. Task Capsule、Extractor 与安全边界

### 6.1 Capsule 内容

Task Capsule 只在进程内存和子进程 stdin 中存在，不写入 Queue、Cache、日志、临时文件、Receipt、Observation 或备份。

默认只处理目标 completed turn，允许包含：

- 任务标题、完成时间、规范项目 scope；
- 当前 turn 中用户明确表达的高信号内容；
- 最终答案中的决策、结果、约束、可复用方法与下一步；
- 必要的高层文件定位，不含文件正文；
- 不含原文的来源 locator。

必须排除：

- system/developer 指令；
- reasoning、思维链、encrypted content；
- 子代理 transcript；
- 完整工具输入/输出、终端日志；
- 长代码、Diff、构建输出和附件正文；
- 其他 turn 的整段历史。

Capsule 目标约 1,200 model token，硬上限 3,000 model token。Phase 1 每个 Revision 只允许一次结构化语义提取调用，不做第二次证据扩展调用；超长内容由确定性预处理器按高信号优先级截断。

### 6.2 两道安全门

1. **Pre-Capsule Gate**：在模型调用前移除已知 secret、凭据模式、明确敏感区段、长代码/Diff/日志和禁止来源类型。
2. **Persistence Gate**：对 Extractor 输出再次做 Schema、长度、来源、sensitivity、个人相关性和禁止内容检查；`sensitive` 与 `secret` 永不生成 Observation。

Receipt 只记录无泄漏计数，例如 `filtered_sensitive_count`，不记录敏感类别细节、原文、摘要或异常堆栈。

Phase 1 不声称确定性规则能在模型调用前识别所有未知敏感语义。启用配置必须明确所用 Extractor 的执行边界；系统能作出的硬承诺是：已知 secret 先清理，且 sensitive/secret、Capsule 与完整 transcript 不进入任何 AGC 受管持久副本。

若 Extractor 使用远程模型，activation 诊断必须显示实际 Provider/模型和“Task Capsule 将产生额外后台模型调用”，并要求显式启用。AGC Hard Forget 只覆盖 AGC 受管副本与备份；Provider 侧瞬时处理、日志或保留策略属于所选 Host/Provider 合同，不能被 AGC 冒充为已删除。

### 6.3 Extractor Adapter

Semantic Extractor 接口只接收 Task Capsule，并按固定 JSON Schema 返回 0–8 条建议 Observation。无足够证据时必须返回 0，不得因为任务很短、只有“继续”或来源含糊而从旧历史脑补事实。

Phase 1 的参考实现是隔离的 Codex 非交互 Extractor：

- ephemeral，不保存自己的 task/session；
- 结构化输出 Schema；
- read-only sandbox 与隔离空工作目录；
- 忽略用户规则和 Skill，避免 Capture 递归调用 AGC；
- 只从 stdin 接收 Capsule；
- 不硬编码模型或供应商，记录实际 extractor/model 版本与 Token 使用；
- 启动前做能力探测；缺少所需隔离能力时不降级执行，而把 Receipt 留在真实 retryable/failed 状态。

未来可以替换为本地或其他兼容 Extractor，但必须通过相同 Schema、安全、Token、重放和隔离测试。

## 7. Capture Receipt

### 7.1 必填 Schema

Receipt 是严格校验的结构化记录。身份、状态与时间字段始终存在；下表标为条件字段的值在相应阶段之前必须为 `null`，不能伪造占位值：

| 字段 | 合同 |
|---|---|
| `schema_version`, `receipt_id` | Receipt Schema；ID 由 Capture Key 确定性派生 |
| `adapter_id`, `adapter_version`, `source_schema_version` | 来源解释版本 |
| `source_root_id`, `task_id`, `revision_id`, `identity_quality` | Capture Key 与身份质量 |
| `source_fingerprint`, `source_hash_schema_version` | load 后必填的来源一致性摘要；load 前为 null；forget-redacted 后清除 |
| `capsule_hash`, `capsule_schema_version` | Capsule 建成后必填；此前为 null；forget-redacted 后清除 |
| `settled_at`, `discovered_at`, `updated_at` | UTC 时间 |
| `status`, `attempt_count`, `next_retry_at` | 状态与重试 |
| `extractor_id`, `extractor_version`, `extractor_schema_version` | extracting 后必填；此前为 null |
| `taxonomy_version` | extracting 后必填；此前为 null |
| `observation_count`, `filtered_counts`, `duplicate_suppression_count` | complete 后必填；此前为 null |
| `token_usage`, `usage_quality` | 本 Revision 全部尝试的模型输入、输出与总量 |
| `redacted_by_forget`, `forgotten_observation_count` | 始终存在；默认 false/0，只能由授权 Hard Forget 改变 |
| `zero_reason` | complete 且 0 条时必填，否则为 null |
| `sanitized_error` | retryable/failed/quarantined 时必填；仅 `stage/code/retryable`，禁止正文与堆栈 |
| `coalesced_to`, `exclusion_reason` | 对应状态时必填，否则为 null |

Receipt 不保存用户文本、模型输出、Observation statement、Task Capsule、异常消息、绝对路径或内容片段。

`token_usage` 在尚未调用模型时为全零，并随每次尝试只增不减。正常 complete Receipt 必须具有 fingerprint/hash；`redacted_by_forget=true` 是唯一允许 complete Receipt 清空这些摘要的例外。

`zero_reason` 枚举为：

- `no_durable_signal`；
- `extractor_empty`；
- `all_filtered_safety`；
- `all_filtered_policy`；
- `all_duplicates_within_revision`；
- `user_forget`。

### 7.2 状态机

| 类别 | 状态 | 是否算成功检查 | 自动行为 |
|---|---|---:|---|
| 运行中 | `discovered`, `queued`, `extracting` | 否 | 继续处理 |
| 待恢复 | `retryable` | 否 | 按 backoff 回到 queued |
| 待预算 | `deferred_budget` | 否 | 获得新预算后回到 queued |
| 成功 | `complete` | 是 | 0–8 条 Observation；同 key 不自动重开 |
| 元数据终态 | `excluded`, `coalesced` | 不适用 | 不做语义提取 |
| 停放 | `failed`, `quarantined` | 否 | 仅显式 retry 或适配器升级后可重排 |

合法转换：

```text
discovered -> queued | excluded | coalesced | deferred_budget | quarantined
queued -> extracting | deferred_budget | excluded
extracting -> complete | retryable | failed | quarantined
retryable -> queued | deferred_budget | failed | quarantined
deferred_budget -> queued | excluded
failed | quarantined -> queued     # 仅显式 retry 或相关版本升级
```

`complete` 可以有 `observation_count=0`，但必须有 `zero_reason`。`deferred_budget`、`failed` 和 `quarantined` 即使存在 Receipt，也绝不能计入成功检查。

`complete`、`excluded` 与 `coalesced` 对相同处理版本默认不可重开。Phase 1 不自动重处理已 complete 的旧 Revision；需要重处理时必须先形成独立设计，定义替换与审计语义。

## 8. Collected Observation

### 8.1 Phase 1 Schema

每条 Observation 至少包含：

| 字段 | 合同 |
|---|---|
| `schema_version`, `observation_id`, `receipt_id` | Receipt ID 由 Capture Key 派生；Observation ID 由 receipt_id + fingerprint 派生 |
| `source` | adapter/root/task/revision 与 opaque locator，不含 fingerprint、摘录或路径；来源摘要只在 Receipt 中保存 |
| `ordinal`, `observation_fingerprint` | Revision 内顺序与幂等摘要 |
| `statement` | 一个原子命题，最多 300 个 Unicode code point |
| `assertion` | subject、mode、modality，沿用 v2 Observation 语义 |
| `primary_category`, `taxonomy_version` | 单一主分类与版本 |
| `kind` | 复用 v2 的 identity/principle/preference/interest/capability/goal/pattern/context |
| `scopes`, `project_scope` | 非空适用范围；无法可靠解析项目时 project_scope 为 null |
| `confidence` | 复用 tentative/observed/confirmed/disputed |
| `sensitivity` | 只允许 normal 或 personal |
| `signal_type` | 为什么可能影响未来协作的受控枚举 |
| `observed_at`, `captured_at` | 发生时间与采集时间 |
| `extractor_version`, `processing_state` | 处理版本；Phase 1 只允许 collected |

Phase 1 的 Observation 持久态只有 `collected`：

- 安全过滤项从不成为 Observation；
- 同一输出内的重复项只增加 Receipt suppression 计数；
- 新 Revision 的相似、矛盾或更新性 Observation 仍按来源分别保存；
- 不自动 supersede、merge、promote 或过期；
- Hard Forget 是物理删除，不是 Observation 生命周期状态。

Phase 1 只持久化 `modality=asserted`。`mode` 允许 `direct`、`behavior_observed` 与带明确依据的 `agent_inferred`；其中 `agent_inferred` 必须是 `confidence=tentative`。`question`、`hypothetical`、`example`、第三方 quote 和无证据心理/人格判断在 Persistence Gate 被过滤，不创建 Observation。

### 8.2 原子性与 0–8 上限

一条原子 Observation 必须：

- 只有一个主要 subject 与一个可判断命题；
- 不用段落、列表或多个“以及”拼接无关事实；
- 区分用户直接陈述、行为证据、Agent 推断、引用、问题与假设；
- 不把第三方事实误写成用户事实；
- 不把缺少任务证据解释为用户没有能力或没有成长。

Extractor 返回超过 8 条时，Runtime 按以下稳定优先级保留前 8 条：

1. 用户直接表达的持久目标、偏好、原则、身份/背景变化和约束；
2. 已验证决策、结果、可复用方法和能力证据；
3. 学习纠正、研究判断变化、开放承诺与下一步；
4. 明确标记且有证据的低影响推断。

同级按来源 locator 稳定排序；超额项不持久化，只增加 `over_limit` 计数。

### 8.3 分类与个人相关性

`primary_category` 枚举：

| 分类 | 判定 |
|---|---|
| `personal_growth` | 用户长期目标、身份、偏好、原则、背景变化或成长轨迹 |
| `research` | 假设、实验、证据、研究判断变化或开放研究问题 |
| `learning` | 新理解、误区修正、技能获得、能力证据或学习下一步 |
| `project` | 对未来协作仍有用的项目目标、关键约束、决策、结果或可复用流程 |
| `work` | 不局限于单一项目的职责、工作流、协作方式和长期工作约束 |

重叠时按“该 Observation 将来主要改变哪类帮助”选择唯一主分类；项目来源不强制分类为 project，仍可分类为 learning 或 research 并保留 `project_scope`。

每条 Observation 还必须通过个人相关性门禁：它应当可能改变未来对用户目标、偏好、能力、方法、协作边界或长期轨迹的帮助。纯项目实现细节、普通代码事实、一次性命令和第三方资料属于项目 LLM Wiki 或原任务，不进入 AGC。

`signal_type` 枚举为：

- `explicit_user_state`；
- `decision_or_constraint`；
- `verified_outcome`；
- `reusable_method`；
- `learning_change`；
- `research_change`；
- `capability_evidence`；
- `open_commitment`。

不保存无证据的人格、动机、心理状态和能力推断。

### 8.4 Project Scope

项目身份解析顺序：

1. 用户显式配置的稳定 project id；
2. 已登记 Git repository/common-dir 身份，使同仓库 worktree 共享 scope；
3. 本地项目注册表中的稳定生成 id；
4. 无法可靠解析时为 `null`，并报告 `project_identity_unknown`，不得用未经处理的绝对路径代替。

项目重命名与 worktree 路径变化通过本地别名注册表关联到既有 id。Observation 只保存不透明 project scope，不保存工作站绝对路径。

## 9. 幂等、事务与崩溃恢复

### 9.1 两层幂等

Capture 幂等键：

```text
(adapter_id, source_root_id, task_id, revision_id)
```

Observation 幂等键：

```text
(receipt_id, observation_fingerprint)
```

`observation_fingerprint` 在安全过滤后，由规范化 statement、assertion、category、kind、scopes、project_scope 与 signal_type 生成，不能使用 ordinal。

因此，一个 Revision 可以安全产生多条 Observation；相同 Revision exact replay 不产生新 Receipt 或 Observation。同一 key 在相同 hash schema version 下出现不同 source fingerprint 时：

- 尚未 complete：Receipt 进入 `quarantined`，不提交 Observation；
- 已 complete：保留原始已提交对象，新增无正文的 quarantined source-conflict 诊断，不覆盖、不创建第二组 Observation，并停止自动处理该冲突副本。

任何 source-conflict 诊断都会把对应 Source Health 标为 degraded，直到用户显式处置或兼容的 Adapter 版本证明它是格式迁移而非内容冲突。

现有正式记忆 `SourceKey(ref, revision, content_hash)` 的全局一次性去重不满足这一合同。Phase 1 必须使用独立 `CaptureStore` 与幂等注册表，不能复用正式记忆 mutation Receipt 作为 Capture Receipt。

### 9.2 Lease 与事务边界

- 每个 Memory Root 只有一个 Capture transaction writer；同一 Capture Key 同时只有一个有效 lease。
- 安全过滤后的 0–8 条 Observation、terminal Receipt 与 Revision processed 标记是一个 journaled transaction。
- Scanner cursor/file hint 在语义事务提交后更新；它失败不会撤销已提交 Observation/Receipt，也不会制造漏采。
- 非 complete Receipt 不得暴露部分 staged Observation。
- 进程退出或 lease 超时后遗留的 `extracting` 必须先经 journal recovery 转为 complete 或 retryable；新 worker 不得直接覆盖 staged 数据。

事务恢复必须得到以下二选一结果：

1. `complete` Receipt 引用的全部 Observation 都可见且 Schema 有效；
2. 该批 Observation 全部不可见，Receipt 回到可重试的真实状态。

任何 crash point 重放后都不得留下 orphan、partial 或 duplicate Observation。

## 10. 存储、备份、恢复与 Hard Forget

### 10.1 独立 Capture Store

- Receipt、Observation、Ledger、Journal 与可重建索引存放在独立 Capture 命名空间，不放入 `memories/` 与 Candidate 目录。
- Receipt 与 Observation 是严格 Schema 的用户可审计结构化文件；索引可由 Source of Truth 重建。
- Catalog builder 必须显式忽略 Capture 命名空间。
- Queue 只保存来源引用和状态，不保存 Capsule 或语义正文。
- 日志只保存计数、状态码和不透明 ID。

### 10.2 Backup 与 Restore

受管 Backup/Restore 必须认识 Capture Schema：

- Backup 包含有效 Receipt、Observation、Ledger 与必要 Tombstone；
- 不包含 Capsule、transcript 副本、staged 临时内容或异常堆栈；
- Restore 后重新校验 Capture Key 唯一性、Receipt/Observation 引用、Ledger 一致性和普通 Recall 隔离；
- 旧版本不认识 Capture Schema 时拒绝不安全 restore，而不是把 Observation 混入 Memory。

### 10.3 Capture Hard Forget

在不增加第四个 MCP Tool 的前提下，`agc.write` 增加显式、需用户授权的 Capture forget action，至少支持精确 `observation_id` 与精确 source Revision 目标。

Hard Forget 必须删除：

- Observation 正文；
- Receipt 中内容派生的 fingerprint/hash；
- Source Quarantine 与其他诊断中的内容派生摘要；
- Capture index、cache、journal 残留；
- Archive、迁移暂存和所有 AGC 受管备份中的匹配副本。

Forget 按两个精确目标执行：

- **精确 Observation**：物理删除该 Observation 及全部受管副本，并在同一事务中更新原 Receipt 的当前 `observation_count`，清空 `source_fingerprint`/`capsule_hash` 及其版本，设置 `redacted_by_forget=true` 并增加 `forgotten_observation_count`。若剩余 Observation 为 0，Receipt 保持 complete 但使用 `zero_reason=user_forget`。它不会被自动重跑。
- **精确 Source Revision**：物理删除该 Revision 的 Receipt、全部 Observation 和内容派生对象，改写所有受管备份，并创建独立的 content-free Capture Suppression Tombstone。Scanner 将 Tombstone 视为明确的“不重新采集”状态。

Capture Suppression Tombstone 只含 Capture Key（或其不透明等价标识）、Schema version、创建时间和 `reason=user_forget`。它不含 statement、内容 hash、证据片段、Capsule、绝对路径或 verification 原文；它不是 Receipt，也不参加 ordinary Recall。

结果必须明确区分：

- AGC 受管 Capture 副本已删除；
- 原始 Codex Task 未被删除。

范围不明确时先澄清，不扩大删除。Phase 1 不做自动 retention/expiry；任何保留期策略都必须在得到真实样本后另行设计，不能静默丢弃 Observation。

## 11. 显式查看与 Recall 隔离

### 11.1 三工具表面不变

公共 MCP Tool 仍只有 `agc.read`、`agc.write`、`agc.admin`。Phase 1 在其内部增加明确 action：

- `agc.read capture_overview`：只返回 Census、状态、覆盖率、分类、项目、Token 与 backlog 统计；
- `agc.read capture_search`：显式搜索 Collected Observation；
- `agc.read capture_get`：按 Receipt/Observation ID 获取受限来源信息；
- `agc.admin capture_status`：报告有效 v2 Skill、Runtime、Memory Root、Source Root、Capture enabled/paused、Hook/Scanner/Runner 状态与路由冲突；
- `agc.write capture_forget`：执行授权后的 Capture Hard Forget。

`capture_search` 默认按 `captured_at` 降序、ID 升序稳定分页，默认 20 条、最大 100 条；支持时间、task、项目、主分类、kind、scope、processing state 与 sensitivity 过滤。来源定位只返回 opaque locator，不返回 transcript 摘录或绝对路径。

### 11.2 普通 Recall 零暴露

- 普通 `overview/search/get/history/evidence` 不读取 Receipt 或 Observation。
- Formal Catalog 不索引 Capture Store。
- Capture 数据不生成 core/scoped card，不自动进入 Prompt。
- 只有显式 `capture_*` action 才能看到 Capture 数据。

Activation Gate 同时修复当前普通 Recall 合同：

- Catalog Card 必须携带 lifecycle；
- 普通 overview/search 默认只包含 `active` Formal Memory；
- 精确 get/history/evidence 仍可按既有权限查看非 active 历史；
- overview 使用单一确定性 estimator，并对完整 accepted response 执行硬预算；即使基础 counts 已超预算，也必须继续压缩或返回明确错误，不能返回 `estimated_tokens` 超过配置值的 accepted response；
- Token budget 与 lifecycle policy 必须来自被 Runtime 实际加载和校验的配置，而不是未使用的装饰配置或分散硬编码。

Capture 未通过这些 Recall Gate 时不得启用。

## 12. 控制与运行

### 12.1 安全默认值

- 新安装或升级默认 `capture.enabled=false`，不得静默扫描历史任务。
- 用户看到 Source Root、Extractor 边界、后台 Token/资源预算和排除规则并显式启用后，才对 Active Profile 的所有 eligible 主任务全局生效。
- `capture.paused=true` 停止新模型调用，但保留 Ledger、backlog 和只读查看；恢复后继续处理。
- `include_subagents=false` 是 Phase 1 固定值，不是可放宽默认值。
- 支持精确 task 与 project 排除；排除产生 metadata-only `excluded` Receipt，不保存任务内容。
- Capture activation 必须报告并拒绝 v1/v2 Skill 路由、多个 MCP Runtime 或多个 Memory Root 的歧义。

### 12.2 重试与 Backpressure

- Runner 默认并发 1；相同 key 只有一个 owner。
- 来源半写、暂时锁定、Extractor 暂不可用和暂时 Schema 输出失败进入 retryable。
- 默认最多 5 次自动尝试，使用可配置 backoff；超过后进入 failed。
- 未知来源身份、相同 key 来源冲突、无法安全解析的格式进入 quarantined。
- failed/quarantined 只能由用户显式 retry，或相关 adapter/schema 版本升级触发重新排队。
- 队列与预算压力通过 `deferred_budget` 或 backlog 暴露，禁止静默 drop。
- 本规格不承诺固定 Scanner 周期或墙钟完成 SLA；它承诺状态不丢、可恢复和最终可重新对账。

### 12.3 路由一致性

启用前 `capture_status` 必须能报告恰好一个有效：

- AGC v2 Skill；
- `agc-mcp` Runtime 版本；
- Memory Root；
- Codex Source Root 集合；
- Capture 配置来源。

发现项目级 v1 Skill 与全局 v2 Skill 同时可解析时，系统必须报告冲突并拒绝 Capture activation。安装器只能在可回滚备份和明确目标下清理旧路由，不得删除未知用户文件。

## 13. Token 与覆盖指标

### 13.1 Token 口径

首次七天回填的所有 Extractor 模型输入与输出，包括 wrapper prompt、重试与无效结构化输出，总和不得超过 100,000 Token。

- Provider 返回的实际 usage 是首选口径。
- Provider 不返回 usage 时，按调用前保留的保守最大额度扣减，并记录 `usage_quality=reserved`。
- 调用前必须预留该调用最大输入与输出；余额不足则不调用，Receipt 进入 `deferred_budget`。
- deterministic 扫描、Hash、Schema 校验和本地文件读取不计入模型 Token，但单独记录运行诊断。
- 持续增量使用独立、显式配置的模型预算；达到预算后延后而不丢失 Revision。
- Phase 1 不绑定具体模型、供应商或 tokenizer；更换 Extractor 不得改变 100,000 总额度的硬约束。

### 13.2 覆盖指标

必须分开报告：

```text
accounting_coverage = 有真实 Receipt 或 Capture Suppression Tombstone 的 Revision Key / Census Revision Key
inspection_completion = complete / (eligible - revision-level suppression tombstone)
silent_loss = Census Revision Key - (Receipt Revision Key ∪ Suppression Tombstone Key)
unresolved = discovered + queued + extracting + retryable + deferred_budget
parked = failed + quarantined
```

另报：

- complete 且 0 Observation 的比例与 zero reason；
- Observation 数量和分类分布；
- duplicate/over-limit/safety/policy suppression 计数；
- Token 使用；
- backlog 与最老 unresolved 时间。
- Source Health 与无法建立 Revision Key 的 source quarantine 数量。

`accounting_coverage` 目标是 100%，`silent_loss` 必须为 0；每个 `coalesced` Receipt 还必须引用有效的 canonical Receipt。`deferred_budget`、`failed`、`quarantined` 会提高 accounting coverage，但不会提高 inspection completion；Revision 级 forget tombstone 只证明已明确抑制，不算成功检查。只要存在无法建立 Key 的 Source Quarantine，Source Health 就是 degraded，即使已知 Census 的 accounting coverage 为 100% 也不能宣称来源覆盖完整。Phase 1 不设置最低 Observation 产出率。

若 inspection denominator 为 0，报告 `inspection_completion=not_applicable` 并同时返回原始计数，禁止用 100% 代替空分母。

## 14. 验收与故障注入矩阵

| ID | 可执行门禁 |
|---|---|
| AC-01 路由与同意 | 诊断只报告一个 v2 Skill/MCP/Memory Root/Active Source Root，并显示 Extractor Provider/模型、后台调用与预算边界；歧义或未显式启用时 activation 被拒绝。 |
| AC-02 Recall Gate | 普通 overview/search 只返回 active Formal Memory；accepted overview 的确定性估算不超过配置硬预算。 |
| AC-03 Census | 含正常、0 条、8 条、超过 8 条、续聊、排除、坏源、迟到记录、活动/Archive 副本的 synthetic census 达到 accounting 100%、silent loss 0。 |
| AC-04 Revision | 同 Task 新 completed turn 恰好产生一个新 Receipt；started、aborted、partial 和 subagent 不被误算成 completed main Revision。 |
| AC-05 Hook | Hook 只产生 metadata Dirty Marker；1000 次代表性测量 added latency `p95 < 100 ms`，否则验证 Scanner-only 自动降级。 |
| AC-06 Scanner | Hook 未安装、重复、取消、来源移动、索引重复与进程重启后，Scanner 集合对账仍恢复完整 Ledger。 |
| AC-07 Observation | 每个 complete Receipt 有 0–8 条合法 Observation；statement、taxonomy、kind、scope、project、sensitivity、locator 与版本均通过严格 Schema。 |
| AC-08 两层幂等 | exact replay 新增 Receipt=0、Observation=0；同 Revision 多条 Observation 不互相误判重复；同 key/different fingerprint 冲突被 quarantine。 |
| AC-09 Crash Recovery | 在 discovery、Observation staging、Receipt final、Ledger processed 与 cursor update 前后注入崩溃；恢复后 orphan/partial/duplicate 均为 0。 |
| AC-10 Safety | secret/sensitive/code/diff/log sentinel corpus 扫描 Queue、Cache、Receipt、Observation、Event、Journal、Archive 与 Backup，禁止内容持久命中为 0；Capsule 文件数为 0。 |
| AC-11 Recall Isolation | 普通 Catalog/overview/search/get 对 Observation 的返回数为 0；只有显式 capture action 可见。 |
| AC-12 Failure Open | 模型不可用、来源锁定、坏输出、预算耗尽与 Runner 崩溃不改变原任务结果，且产生真实非成功状态。 |
| AC-13 Backpressure | 默认 concurrency=1；并发相同 key 只有一个 lease owner；预算/积压不 drop Revision。 |
| AC-14 Controls | enabled/paused、task/project exclude 与 scanner-only 均可诊断、可恢复；excluded 无内容持久化。 |
| AC-15 Token | 七天回填按实际或 reserved usage 累计不超过 100,000；余额不足的 Revision 为 deferred_budget。 |
| AC-16 Read Views | capture overview/search/get 的过滤、稳定排序、分页、空结果、来源限制与敏感过滤都有契约测试。 |
| AC-17 Backup/Restore | Capture 数据 round-trip 后 Schema、引用、Ledger、幂等和 Recall 隔离保持成立。 |
| AC-18 Hard Forget | Observation 级 forget 后 Receipt 计数与 redaction 不变量成立；Revision 级 forget 后只保留 content-free suppression tombstone。两者在所有 AGC 受管正文和内容摘要中的命中均为 0，且原 Codex Task 不受影响。 |
| AC-19 Format Drift | 未知 transcript identity/completion 形态 fail closed：有稳定 Key 时写 quarantined Receipt，无稳定 Key 时写 Source Quarantine 且 Source Health=degraded；adapter/hash schema 升级不被误判成同版本来源冲突。 |
| AC-20 Release Gate | 新增测试、完整既有测试、package、installer、部署 Profile 诊断、严格 UTF-8/no-BOM 与 `git diff --check` 全部通过并记录原始证据。 |

实现计划必须把每个 AC 映射到独立可运行测试，不允许只写“测试通过”。Verification Record 还必须记录生产代码、测试代码、mock、assertion、实际行为和残余风险，避免用过度 mock 代替真实 Source/文件/进程验证。

### 14.1 Change Brief 追踪

| Change Brief Acceptance | 本规格门禁 |
|---|---|
| 1 唯一路由与诊断 | AC-01, AC-14 |
| 2 普通 Recall lifecycle/budget | AC-02 |
| 3 七天 Census 每个 Revision 有真实状态 | AC-03, AC-04, AC-19 |
| 4 持续增量与 coalesced 关系 | AC-03, AC-04, AC-06, AC-08 |
| 5 Hook 只做元数据唤醒 | AC-05 |
| 6 Runner + Scanner 最终对账 | AC-06, AC-12 |
| 7 每个 complete 为 0–8 条 Observation | AC-07 |
| 8 Task/Observation 两层幂等 | AC-08 |
| 9 原子提交与崩溃恢复 | AC-09 |
| 10 禁止敏感/原始内容持久化 | AC-10 |
| 11 显式查看且普通 Recall 零暴露 | AC-11, AC-16 |
| 12 Failure-open | AC-12 |
| 13 Hook p95 门禁与 Scanner-only | AC-05 |
| 14 单并发、backpressure 与状态统计 | AC-13, AC-16 |
| 15 pause 与 task/project exclude | AC-14 |
| 16 七天回填 100,000 Token | AC-15 |
| 17 Capture Backup/Restore | AC-17 |
| 18 Capture Hard Forget | AC-18 |

## 15. Rollout 与 Rollback

Rollout 顺序：

1. 统一 v2 路由并通过 Recall Gate；
2. Source Adapter 以 census-only 模式运行，不调用模型；
3. 验证 main/subagent/revision 分类和 synthetic census；
4. 验证 Hook 延迟；不通过则 Scanner-only；
5. 显式授权后运行七天 Shadow Backfill；
6. 用户通过 capture views 检查样本、安全与分类；
7. 再启用持续增量。

Rollback：

- 关闭 Hook、Runner 与 Scanner 的新处理；
- 保留现有 Capture 数据的只读查看与 Hard Forget 能力；
- 不回滚或修改 Formal Memory，因为 Phase 1 从未自动写它；
- 恢复处理时从 Ledger 和 Receipt 继续，不重新扫描全部历史；
- 如需删除 Capture 数据，必须走用户授权的 Hard Forget，不用卸载脚本静默删除。

## 16. 明确延期与不承诺事项

Phase 1 不实现或不承诺：

- Observation 跨 Revision 语义去重、聚合、冲突裁决、Candidate 或 Formal Memory 晋升；
- 自动 reinforce/update/supersede/archive 正式记忆；
- Observation 自动 retention、expiry 或基于容量的静默删除；
- 向量数据库、知识图谱、TencentDB Agent Memory 或远程多用户服务；
- Trace/Eval/Loop、应用效果、成长建议质量或正式记忆增长指标；
- 子代理独立采集、全历史回放、完整 transcript 存储；
- UI Dashboard、团队 ACL、跨设备同步；
- 固定 Scanner cadence、墙钟 eventual SLA、100% Extractor 成功率；
- 固定模型、供应商、tokenizer 或 transcript 私有格式长期稳定。

Phase 2 只有在 Phase 1 已积累可查看样本，并由用户确认分类质量、噪声与安全边界后，才设计 Observation → Candidate → Formal Memory 的闭环。

## 17. 设计依据

- AGC v2 总体设计：`docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md`
- Change Brief：`.llm-wiki/requirements/agc-capture-coverage-mvp.md`
- Working Context：`.llm-wiki/working-context/agc-capture-coverage-mvp.md`
- Codex Hooks：<https://learn.chatgpt.com/docs/hooks>
- Codex 环境与状态位置：<https://learn.chatgpt.com/docs/config-file/environment-variables>
- Codex 非交互模式：<https://learn.chatgpt.com/docs/non-interactive-mode>

这些 Host 文档只用于界定 Hook、Profile 与 Extractor 能力。Source Adapter 仍必须把 transcript 当作版本化私有格式处理，并用 Scanner、Ledger、Receipt 与 fail-closed 隔离保证 AGC 自身的正确性。
