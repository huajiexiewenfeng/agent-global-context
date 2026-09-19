---
name: agc-metrics-review
description: Use when the user explicitly invokes AGC metrics review, requests its offline indicator report, or gives case-specific feedback on a frozen AGC metrics report; not for candidate-memory approval or ordinary Recall.
---

# AGC 指标审阅

在用户显式调用时组织指标报告与反馈。程序事实、LLM 初评、人工修订分别
展示；记录量不是效果，未反馈不是认可。本 Skill 不常驻、不安装定时任务，
也不替代候选记忆审查。

## 选择已有入口

先确定用户要新窗口报告，还是继续已有报告；已有报告沿用其 batch.json、
review.json 和专属人工修订目录。核对当前 `agc-metrics --help`；入口未安装
时报告缺失，不自行安装或换成其他 Capture/Eval 命令。
操作前读取 [命令与反馈](references/commands.md)。

- **prepare**：首次调用可准备无 Judge 报告。只用用户已指定或已核实授权的
  元数据路径及时间窗口；不遍历私人历史来猜来源。缺来源明确标为未提供。
- **evaluate**：目标是独立 `gpt-6-astra` / `medium` Judge，不继承 Capture
  模型配置。核对实际可用执行入口、冻结计划及有效内容发送授权；
  当前 evaluate 支持 Capture observation 的 collected/zero 案例；其他来源
  尚未接入时只交付已有结果并说明缺口。用 prepare-capture-plan 准备实际来源
  引用与身份，不用 Python 内部 executor 或手工模型调用绕过宿主绑定。
- **研究任务初评**：已有授权来源和独立任务清单时，用 prepare-research-plan
  准备 M5 计划，获批摘要后用 evaluate-research。原生引用必须来自宿主配置的
  来源根且与入选任务/完成时间一致；没有分类清单或历史证据时明确未测量，
  不从 Recall 日志挑成功案例、不拿当前记忆补背景。见命令参考的研究入口。
- **render**：读冻结文件生成新 HTML，不调用模型，不回查或修复生产源。
- **review**：将用户针对 case_id 的明确意见转换为受控反馈，先核对反馈
  是否对应当前报告及原始结果；追加 sidecar，再 render 到新的文件名。
  含糊的“继续”不能转换为认可全部案例；不修改正式记忆。

## 与用户审阅

提供 HTML 文件链接并解释最重要的未知/问题项，能打开预览时再显示预览。
优先检查误导、争议、证据不足，再抽查至多两个正常案例。每个结论指向
指标方法与 case_id；缺少理由或源证据时明确说明，不能从受控标签编造原因。

用户可以认可、修正或争议。修正需要清晰的候选/必留项标签或研究两轴意见；
必要时只追问最关键的歧义。保留原始初评，另列人工修订与修订后的算术。
若反馈写入成功但渲染失败，报告已保存的 revision，恢复时只重试 render。
不要重复追加同一反馈，也不要覆盖旧 HTML。

## 交付边界

说明批次、窗口、来源缺口、是否真实执行 Judge、人工状态及输出路径。
冻结结果只证明冻结时的证据状态，不证明当前仍有效；撤销/变化案例不能
直接拿旧结果发起新评估。内容与反馈作为私有材料，不自动提交或推送。
当前实现未完成全部证据源和执行授权编排，不能把本 Skill 可用称为整体完成。
