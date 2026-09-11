# AGC Capture Supervised Improvement Loop Implementation Plan

> For agentic workers: execute inline through project-develop and TDD. Do not dispatch additional agents or invoke models for this offline slice.

**Goal:** 建立可运行、可测试的离线实验骨架，再在单独授权后完成真实两轮实验。

**Architecture:** AGC 领域模块接受显式注入的提取函数和外部评审记录，校验样本与版本后产生逐项比较。仅用标准库，不导入生产 Runner、MemoryPaths 或模型客户端；工程演示不代表真实模型收益。Trace/Eval/Wiki 接入留在后续同一需求的集成阶段，未接入不能宣称全闭环完成。

**Tech Stack:** Python >=3.10, pytest, JSON-compatible records, SHA-256.

## Global Constraints

- flow_id: agc-capture-supervised-improvement-loop
- specification: ../requirements/agc-capture-supervised-improvement-loop.md
- 不更改生产配置、正式记忆、自动 Runner、Schema 或提取规则。
- 本轮不生成真实盲测题；24 条工程合成样本明确标记为 development fixtures。
- 用例内容和标签不进入候选提取函数：仅传 case_id 和 input。
- 同族样本不能跨集合；输入、模型/Schema/Profile 配置必须可比，只有 Prompt 可变化。
- 所有临时运行产物使用用户指定的统一测试根目录；不自动提交或推送。

## Task 1: 离线 Harness 与回归测试

Files: create `agc_runtime/capture_experiment.py`, `tests/test_capture_experiment.py`, `tests/fixtures/capture_experiment/development.json`.

Interfaces:

```python
validate_suite(cases: list[dict]) -> None
run_batch(cases: list[dict], *, split: str, identity: dict, extractor: Callable) -> dict
compare_runs(baseline: dict, candidate: dict, assessments: list[dict]) -> dict
round_receipt(report: dict, *, proposal_ref: str, lesson: str, previous: dict | None = None) -> dict
```

- [x] 写契约测试：重复 case_id、同族跨集合；提取器只收到输入；提取异常返回错误状态而非成功 zero。
- [x] 运行聚焦 pytest，确认缺失新模块/API 导致 RED。
- [x] 实现最小数据校验和批次执行；输入摘要绑定完整用例，输出引用绑定内容摘要；错误不回显异常文本。
- [x] 比较测试覆盖：异模型/异样本拒绝比较；缺评审返回错误；越界证据拒绝；目标改善但遗漏增加不得接受；相同结果为 inconclusive。
- [x] 实现比较：验证完整双侧逐项评审、证据引用和非负整数指标，保留逐项差异与总计；运行失败不能算质量差或满分。
- [x] 两轮记录测试覆盖：第二轮显式绑定第一轮记录与经验解释；相同输入重复生成相同 receipt_id；失败尝试仍可被后续引用。
- [x] 实现无副作用 round_receipt，持久存储交由后续领域知识适配器，不重复建立数据库。

验证命令（仓库根目录，使用已具备 pytest 的解释器；临时目录置于用户指定测试根）：

```text
python -B -m pytest tests/test_capture_experiment.py -q -p no:cacheprovider
python -B -m pytest tests/test_capture_eval_adapter.py tests/test_capture_eval_evidence.py tests/test_capture_eval_end_to_end.py -q -p no:cacheprovider
git diff --check
```

验收断言示例：

```python
assert report['recommendation'] == 'reject'
assert report['totals']['candidate']['durable_omissions'] > 0
assert second['previous_receipt_id'] == first['receipt_id']
assert second == round_receipt(report, proposal_ref='candidate:2', lesson='Avoid the first rejected change', previous=first)
```

## Task 2: 模型实验前的集成边界（后续用户已授权离线集成）

Current slice files: `agc_runtime/capture_experiment_integration.py`, `tests/test_capture_experiment_integration.py`, `templates/agc-experiment-profile.yml`.

Interfaces: `evaluate_batch(run, cases, *, profile, judge, eval_service, eval_store, trace_service)` binds safe inputs and outputs to real Eval results, with AGC-side evidence membership validation before generic Eval persistence. Trace covers evaluation lifecycle only. `save_round(receipt, report, *, evaluation_batches, eval_store, trace_service, scope_root, profile_path)` checks referenced results and traces before writing a create-only isolated Wiki record. Optional providers are imported only inside integration functions.

- [x] RED: module absent; then tests caught incomplete evidence coverage and an overwrite-capable Wiki profile.
- [x] GREEN: implement the minimal AGC bridge, preserving raw content outside Trace and generic Eval results.
- [x] Test using actual local runtime source/providers in one isolated process; simulated Judge only. No dependency installs, external model calls, production roots, or general runtime repository edits.
- [x] Record scope limits: synthetic provider integration is not human semantic annotation, sealed holdout evaluation, or production activation.

- 源码验证真实 Capsule、Extractor、Eval、Wiki 公共接口，接通离线 roots 与实际版本。
- 独立建立并冻结 12/6/6 样本与人工标注；本轮公开工程 fixtures 不得冒充未见验收集。
- 校准 zero/短期证据评分规则，检查证据引用和所有失败类别；Trace/Wiki 接入需要实际记录回读验收。
- 输出真实模型调用的输入范围、次数与预算/停止条件，取得授权后才调用。

## Task 3: 两轮真实改进与最终验收（授权后）

### Resumed offline preflight — 2026-09-07

- Resume the existing Flow through project-develop; documentation mode: update existing requirement/plan. No new lifecycle or external repository scope.
- Add `capture_experiment_preflight.py` and focused tests to derive source/Schema/Profile/Prompt fingerprints from the explicit AGC checkout, without importing that checkout or invoking a subprocess/model.
- Keep candidate Prompt as an explicit in-memory override; do not edit production extraction instructions. Bind model configuration as declared configuration, not verified service identity.
- This is a preparation snapshot, not proof of the executable used by a future run. Actual execution binding, reviewed labels and model authorization remain pending.
- Verification: missing-module RED, content-change/Prompt-only/invalid-artifact tests, then adjacent offline regression. No production writes or Git push.

- 冻结初始基线，按规格执行两轮，每轮仅一个 Prompt 修改。
- 用真实 Trace、Eval、经验记录串起输入、输出、评估、接受/拒绝及下一轮引用。
- 独立验收同时对比当前与初始基线；复跑确认波动，证据不足明确保留。
- 单独申请生产发布；闭环未验收前不增加自动计划任务。

## Scope review

Task 1 只验证数据与控制边界，不覆盖真实语义质量、独立盲测、持久幂等、Trace/Eval/Wiki 集成和生产发布。Task 2/3 是剩余工作，不因离线测试通过而标记完成。

## Offline verification — 2026-09-05

- Branch: `codex/agc-capture-loop`; no commit/push or production installation.
- RED: new module absent; then two regression tests failed for cross-round context mismatch and callback mutation of identity.
- GREEN: 26 new tests passed. Combined targeted regression: 49 passed, 1 skipped.
- Full offline regression: 1453 passed, 1 skipped, 1 expected duplicate-ZIP-name warning in 593.20 seconds. Slow existing Windows installation tests used isolated temporary venvs, not the production installation.
- UTF-8/no-BOM checks passed for all five new artifacts; tracked diff whitespace checks passed. No Ruff result is available.
- Skip: existing `test_capture_eval_end_to_end.py` requires optional Trace/Eval dependencies absent from the development venv. No claim of end-to-end Runtime integration.
- Ruff unavailable in both checked Python environments; no lint-pass claim.
- Fixtures: 24 synthetic, exposed, development-only, annotation_status=unreviewed. Empty required/forbidden arrays are unreviewed placeholders, not gold labels and not semantic acceptance evidence.
- Recommendations stop at reject/inconclusive/rerun_required; no automated accept or publication. Counts are externally adjudicated, not inferred by this module; no claim-level rates are computed before reviewed denominators exist.
- Hashes verify record consistency, not reviewer identity/authenticity. Previous-receipt linking verifies fixed experiment context, not whether the written lesson is semantically useful; that remains human-reviewed.
- Identity fields are caller-supplied metadata in this skeleton; deriving them from actual executable/model/Prompt artifacts belongs to the integration stage.

## Provider integration verification — 2026-09-05 follow-up

- New integration tests plus offline core and existing Capture Eval regression: **55 passed, zero skipped in 5.34 seconds**. The existing end-to-end test used its local fake Codex subprocess, not an external model.
- Real providers: TraceService/EventStore, EvalService/EvalStore, Wiki init_profile/write_record/load_context_pack. Stores were created only inside isolated synthetic test scopes. No end-user home/domain initialization or global configuration change.
- The initial optional-dependency skip was resolved for this test process through explicit local source paths; no pip install or production dependency change.
- Agent Runtime Modules revision: `d53dc4f5cdd59731f063fe3680c183cfb658ef81`.
- LLM Wiki Runtime revision: `ce060ecffb58a4edb3b9151d6e5b2d029be1a7cf`, with pre-existing uncommitted `llm_wiki_runtime/io.py` changes. Tested file SHA-256: `6c2dba8e025f6f5cb2fc3f14c669fddbe55d9e44274aea88164d68c1cdb8935f`. Existing untracked files also left untouched. This is current-local-source evidence, not a clean-release qualification; pin/resolve the dependency state before a production rollout.
- AGC validates Judge citations before generic Eval persistence, and includes a guard version in the Judge cache identity. Out-of-case citations yield evaluation_error, never pass. This does not repair the generic Eval package for other consumers.
- Trace describes evaluation lifecycle, not retrospective Capture lifecycle. Item events link run/case/result IDs without source text or extracted statements.
- Wiki stores provisional round/report/provider references using a fixed create-only experiment profile. Writes verify referenced Eval results and Trace events; duplicate content returns already_exists, mismatched content fails without overwrite. The scope is separate from AGC user memory.
- Cross-store operations are not one transaction. Errors remain visible; this slice does not implement general Recovery or guarantee atomic three-store commit.
- Remaining: deriving real execution identity, full runtime-native Capture payloads, independently reviewed labels, sealed holdout boundary, real-model authorization, meaningful two-round improvement and final quality acceptance. No claim that synthetic all-pass Judge results demonstrate semantic improvement.
- Regression scope: focused integration/adjacent tests only in this follow-up; the previous 1453-test full run predates this integration file. No second slow installer-suite rerun was needed for an opt-in bridge with unchanged production entry points.

## Preflight verification — 2026-09-07

- Added read-only `prepare_identity`: hashes AGC Python sources and build metadata, actual extraction instruction, output Schema and Eval Profile. Reads source via AST without importing the inspected checkout. Model settings are explicitly declared and hashed, not service-attested.
- A candidate Prompt override changes only the Prompt identity and never writes the production instruction. Source, Schema and Profile edits change the corresponding fingerprints; invalid/missing artifacts fail preparation.
- RED: all nine new tests failed because the new module was absent. GREEN: 35 preflight/core tests passed; final preflight/core/Trace/Eval/Wiki adjacent regression **64 passed in 4.70 seconds**, with no skipped tests. Models remained simulated. Tracked whitespace check passed with existing LF/CRLF conversion warnings only.
- Snapshot output contains relative artifact names and hashes, not source text or local absolute paths. It explicitly reports `execution_verified=false` and `model_called=false`.
- This does not bind the future subprocess executable, actual model response identity, or request bytes. The caller must still wire the snapshot into the real Capsule/Extractor execution path; a saved snapshot alone is not authorization or execution proof.
- No model authorization digest is ready yet: reviewed sample payloads, frozen scoring rules and exact request bounds are still missing. Do not ask the user to approve an invented digest or reuse a historical Capture authorization.
- Next gate: implement a dry-run request binding using the existing safe Capsule serialization; then reviewed labels and the bounded first-round authorization summary. Production installation and Git push remain excluded.
