# 当前命令与反馈合同

以已安装 `agc-metrics --help` 和各子命令帮助为准。源码开发环境可由维护者
使用 `python -m agc_runtime.metrics_cli`；普通审阅不得自行修改环境或安装。
当前支持 prepare、plan、prepare-capture-plan、evaluate、research-inputs、research-cohort、
prepare-research-plan、evaluate-research、prepare-classification-plan、classify-research、
export-classification、export-review-evidence、render、review。只有 evaluate、evaluate-research 和 classify-research 可调用
模型；分类调用与质量 Judge 分开授权，其余入口均不调用模型。

## Capture 初评宿主与执行

宿主绑定位于当前用户目录下 `.agent-global-context/metrics/host.json`，共享
账本固定为同目录的 send-ledger，不接受按报告传入或环境变量覆盖账本位置。
两者均需安装阶段显式准备；缺失时停止，不自动新建账本来重新获得调用额度。
host.json 严格字段为 schema_version=agc.metrics-host.v1、memory_root、
source_roots（目录列表）、executable（绝对命令文件路径列表）、model、
reasoning_effort、timeout_seconds。初期使用 gpt-6-astra / medium，独立于
Capture 配置。只有配置/可执行绑定与冻结计划一致才可执行。

`prepare-capture-plan --batch <文件> --references <原生 Capture EvidenceRef 列表>
--output <新目录>` 生成 plan.json 与 source-map.json，不保存 Capsule 正文。
原生引用来自已授权读取的既有 Capture 证据，不从猜测构造 receipt/digest。
此入口目前仅支持 observation 的 collected/zero 分层。

用户明确批准计划摘要后，使用 `evaluate --batch <文件> --plan <plan.json>
--source-map <source-map.json> --consent <获批摘要> --output <已有私有执行目录>`。
授权摘要不是用户同意的证明；已有明确授权不重复询问。固定账本在每步发送
前预留，失败不退额度；错误不自动重试。同执行目录的合法结果会重新核验并
复用，变化/缺失证据拒绝复用。新目录不会绕过已有调用预留。
该命令追加 run/review/report 的带唯一后缀文件，返回实际路径、调用尝试数
及逐步状态；命令成功产出报告不等于所有案例评估成功，逐步错误仍须报告。
中断后保留尝试；不删除目录重新发送。显式重新授权重试接口仍待实现。

## 准备与计划

### 研究任务入口

分类已支持显式两步命令：

```text
agc-metrics prepare-classification-plan --batch batch.json --references native-revisions.json --output NEW_PLAN_DIR
agc-metrics classify-research --batch batch.json --references native-revisions.json --plan NEW_PLAN_DIR/plan.json --consent EXACT_APPROVED_DIGEST --output EXISTING_PRIVATE_RUN_DIR
```

准备命令只保存 plan.json 和无正文 preparation-manifest.json，不调用模型。
先向用户展示计划的任务数、模型配置、最多调用数与授权摘要，获得明确授权
后才执行第二步；命令中的占位符不是授权。模型与账本来自固定 host.json
及 send-ledger，不能另建账本绕过重复限制。失败也消耗单次调用，不自动重试。
执行返回 classification_status；外层 status=ok 只表示流程返回，不代表分类
成功。completed 的执行目录包含 classification.json（含 cohort）、receipt.json
和 finished.json；尚不可把任意目录里的结果当作经过来源复查的可复用结果。
分类不是质量 Judge；后续评估仍须单独准备计划并授权，不自动调用。

分类成功后，使用只读校验并导出清单的命令（读取已授权范围的来源，不调用模型）：

```text
agc-metrics export-classification --batch batch.json --references native-revisions.json --plan NEW_PLAN_DIR/plan.json --execution-dir EXISTING_PRIVATE_RUN_DIR --output NEW_COHORT_DIR
```

导出 research-cohort.json 与 classification-verification.json，后者保留完整
准备清单及校验时间。只有通过当前来源、完成记录和账本一致性检查才导出；
不覆盖已有目录。这是当时的一致性检查，不是永久授权或分类正确性的证明。
把 research-cohort.json 交给 prepare-research-plan；其 --references 只传清单
selected_task_refs 对应的原生引用，最多 5 条，不把全部分类引用直接传过去。
准备 M5 计划不调用模型，执行仍需要独立的评估摘要授权。

人类查看报告时，render 可增加 `--research-cohort NEW_COHORT_DIR/research-cohort.json`，
展示分类选择状态与原因，不调用模型或回查来源。该清单不自动成为 M5 质量
分母；还需单独看 preparation manifest 中未分类/超限/缺失输入，不能把零
入选解释为没有研究任务。冻结清单与初评案例的逐项对应关系不由此展示证明。

还可增加 `--research-preparation NEW_PLAN_DIR/preparation-manifest.json`，直接
显示准备阶段的 5 类状态和逐引用明细。此参数只接无正文 manifest，不接含
私有 inputs 的完整 research-inputs 返回包。分母为引用条目，ready 不等于
分类成功；不把两张图自行拼成未经核验的成功率。

若用户明确要求查看私有证据明细，并已有经过核验的同批附录，render 可传
`--evidence evidence.json --review review.json`。HTML 只显示经校验的状态和引用，
不嵌入来源正文或未经检查的模型理由。清理机制未接好前不要新建正文附录文件。
渲染不回查来源或自动刷新撤销状态；缺失附录时不能手工拼接内容绕过校验。
自动失效清理仍未完成，不宣称生产端已支持自动管理。

明确需要核验证据关联且来源读取范围已授权时，可生成受控引用索引（不重跑模型）：

```text
agc-metrics export-review-evidence --batch batch.json --review review.json --source-map source-map.json --execution-dir EXISTING_RUN_DIR --output NEW_PRIVATE_EVIDENCE_DIR
```

研究计划还必须传 `--cohort research-cohort.json --references selected-native-revisions.json`；
Capture 计划不要传这两个参数。命令从固定宿主重查来源，输出 evidence-index.json
和无正文 report.html；available/unavailable 案例数单列，导出成功不等于证据完整。
只支持单类来源的计划，不支持 Capture 与 research 混合计划；不覆盖已有目录。

`research-inputs --batch <文件> --references <原生 RevisionRef 列表>` 可准备
显式授权范围内的分类输入，最多 100 个引用；无模型调用，不写文件。返回
research_preparation，其中 manifest 只有引用/摘要/状态，inputs 含私有的
安全用户输入，不能提交到 Git、复制到公开报告或无授权发送给其他模型。
窗口外不读正文；同任务多个窗口内修订标为 ambiguous_revision，不默默挑一个。
准备不返回回答正文，避免按答案好坏选样；失败条目仍保留 evidence_unavailable。
inputs 的规范 UTF-8 JSON 数组累计上限为 2 MiB；按完成时间、任务和引用固定
排序，放不下的正文不返回，清单保留 input_budget_exceeded 及版本/摘要引用。
不截断正文，也不丢弃清单；后续较小输入仍可返回，因此不能当作随机抽样。
此命令尚不执行语义分类，也不证明原生引用列表覆盖整个窗口。不可把
classification_status=not_classified 当作已识别的研究任务；后续分类及其模型/
授权记录仍需明确工作流，不要求用户逐条手工打标签作为替代实现。

已有独立任务分类元数据时，`research-cohort --batch <文件> --tasks <元数据>
--classifier <分类规则与来源> --output <新目录>` 冻结清单；不自动发现或分类
会话。保留歧义、排除和缺失状态；不把零入样等同于没有研究任务。

`prepare-research-plan --batch <文件> --cohort <research-cohort.json>
--references <原生 RevisionRef 列表> --output <新目录>` 生成 plan.json 和
source-map.json。原生引用只包含入选的至多 5 个任务，须来自已授权范围，
不猜 locator/修订 ID；来源根必须在固定 host.json 中。准备会读取这些历史
任务的输入和明确最终回答，但不调用模型。准备结果不含正文。

获批摘要后，`evaluate-research --batch <文件> --cohort <清单> --references
<相同原生引用> --plan <plan.json> --source-map <source-map.json>
--consent <获批摘要> --output <已有私有执行目录>` 使用同一固定发送账本。
它核验任务时间、版本、实时 Capture 遗忘/排除；复用与错误规则同 evaluate。
历史背景/论文来源的独立证据提取尚未接通，不能将背景准确性 unknown 说成
正确，也不能根据已有输出推断 AGC 因果收益。当前任务分类来源仍需授权流程
提供；不要求用户手工逐项预标注，也不以伪造标签补齐缺失清单。

`prepare --start <含时区时间> --end <含时区时间> --cutoff <含时区时间>
--output <新目录>` 可带明确路径的 `--trace-db`、`--eval-db`、`--receipts-dir`、
`--attempts-dir`、`--business-dir`。不提供的来源记为缺失，不计作正常空结果。
生成 batch.json、metrics.json、report.html。不要将生产数据标为 synthetic。

`plan --batch <文件> --cases <文件> --judge <文件> --rules <文件> --output <新目录>`
生成冻结计划及授权摘要，不是发送许可。case/规则和 executable/adapter 身份
应由已验证来源适配器生成；不能从随意文本猜 digest。尚无准备好的输入时
先交付元数据报告并说明未初评，不补造案例。

## 追加反馈并重渲染

以下示例在用户指定的私有报告目录执行。batch.json 和 review.json 必须同批；
human 是已存在、专属于该报告的修订目录，初次使用时为空。
feedback.json 从本次用户明确意见构造，字段必须恰好是：

- case_id：原报告案例 ID。
- decision：accepted、corrected 或 disputed。
- correction：accepted/disputed 为 null；corrected 为下述受控投影。
- feedback_ref：实际反馈来源的不透明 `id_` + SHA-256 引用；摘要不是身份认证。
- timestamp：实际反馈记录时间，含时区且不早于报告截止；不伪造或回填时间。

corrected 的 correction 包含 candidate_verdicts、required_matches、research。
M2 前两项是列表，research=null；M5 前两项=null，research 为 relevance、
misleading、background_accuracy、issues。保持原案例阶段/对象/结果关联。
候选标签 supported/unsupported/unsuitable_durable/uncertain；必留项包含
certainty(required/uncertain) 和 verdict(retained/omitted/uncertain_match)。
研究 relevance 为 specific_useful/partial_or_generic/no_supported_link/
insufficient_evidence；misleading 为 yes/no/unknown；background_accuracy 为
supported/inaccurate/unknown；issues 仅允许 inaccurate_background、
unsupported_connection、hypothesis_as_fact。源正文、自由文本原因不放入此文件。

```text
agc-metrics review --batch batch.json --review review.json --feedback feedback.json --revisions-dir human
agc-metrics render --batch batch.json --review review.json --revisions-dir human --output report-revision.html
```

第二次 render 选择新的输出文件名。仅渲染时不必追加反馈；无人工修订目录
可省略 --revisions-dir。没有 review.json 时省略 --review，只显示元数据报告。
文件损坏、身份不匹配、重复 JSON 字段等错误需报告；不删除历史或手改摘要。
每次 review 追加新 revision，不提供自动幂等重试：响应不确定时先核对
已有 sidecar 是否匹配此次反馈；成功后只重试渲染。

## 方法与解释

HTML 的五项“查看方法”是当前批次计算口径。M2 分层/版本不同不混算，零
分母不可计算；M4 使用计划案例而不是模型调用次数作覆盖分母；M5 的联系
质量与误导是两个轴。人工修正后视图混合未修改初评与明确修正，不能当作
全部经人工认可。无对照不得称 AGC 增量收益；无独立修复证据不得称 Trace
已推动改进。Skill 本身不判断新旧实现优劣、不自动修复系统。
