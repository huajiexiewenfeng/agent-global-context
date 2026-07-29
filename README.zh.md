# Agent Global Context

[English](README.md) | 简体中文

面向 AI Agent 的 Markdown-first 个人长期记忆。

Agent Global Context 的目标是让 Agent 记住一个真实且会变化的人，在工作、生活、学习和研究中持续提供支持，同时不让记忆变成 Prompt 噪声。它不是完整聊天归档，而是一个只保留高价值信息、可审计的个人上下文层。

## 为什么需要它

长对话最终会遇到上下文限制和压缩。常见做法是总结所有内容，但全量总结很快会变得嘈杂，也难以信任。

这个项目采用另一种方式：

- 只保存高价值上下文，不保存完整聊天记录。
- 使用 Markdown，让上下文可读、可编辑、可审查。
- 按优先级和任务相关性读取，而不是一次性加载所有内容。
- 自动捕获保持安全：候选先进入 staging，不直接进入长期记忆。
- 保持 agent-neutral：可用于 Codex、Claude Code、Cursor、OpenCode，以及其他支持 skills 或 instruction files 的 coding agent。

## North Star

- 记住“人”，而不只是当前项目。
- 帮助人在工作、生活、学习和研究中成长。
- 只使用足以改善当前结果的最少记忆；无关时保持安静。

## v2 记忆模型

v2 将分类、生命周期、置信度、时间属性、召回元数据、敏感度和来源证据分开表达，并采用渐进读取：

```text
overview -> search -> get -> history/evidence
```

系统默认不注入任何个人 Memory Card。LLM 自主决定是否需要记忆、读取什么以及是否采用；召回元数据只是先验提示，不是固定 Prompt 注入规则。

普通记忆和满足条件的个人记忆仍以可读 Markdown 保存。v2 的 sensitive 持久化固定为 `disabled`，secret 永不保存。

## Runtime Foundation

仓库现在包含一个独立、确定性的 Python Runtime Foundation，负责 Schema、严格 UTF-8 I/O、生命周期门禁、精确来源键幂等、Markdown 存储、脱敏事件、渐进读取、Hard Forget、校验、备份与恢复。

Runtime 不判断两段自然语言是否语义相同，也不会自行生成 `match_memory_id`；这些语义选择仍由 LLM 负责。

它向 Host 暴露三个结构化工具：

```text
agc.read
agc.write
agc.admin
```

本地 CLI 只是 Host Adapter，不是要求人手工操作的工作流：

```text
agc read  --root <path> --input <json-file|->
agc write --root <path> --input <json-file|->
agc admin --root <path> --input <json-file|->
```

Codex 旁路采集和 v1 迁移属于独立 rollout 计划，本次 Runtime Foundation 不会自动启用它们。

## 快速开始

1. 使用 `npx` 安装 skills。

```bash
npx skills add huajiexiewenfeng/agent-global-context
```

这会安装全部五个 skills：

```text
skills/agent-global-context/
skills/agent-global-context-recall/
skills/agent-global-context-commit/
skills/agent-global-context-capture/
skills/agent-global-context-review/
```

2. 创建 memory root。

```text
~/.agent-global-context/
```

3. 复制 memory 模板。

```text
templates/memory/* -> ~/.agent-global-context/
```

4. 添加 agent instruction。

```text
At the start of substantial work, use agent-global-context-recall.
Use agent-global-context-capture for strong durable context signals.
Use agent-global-context-review when candidate review is suggested.
Use agent-global-context-commit when the user asks to remember something or compress a session.
```

5. 试一下基本流程。

```text
Load my global context.
Remember that I prefer design discussion before implementation.
Review my pending global context candidates.
Compress this session into global context.
```

## Runtime 过渡期的 Alpha Skills

- `agent-global-context`：共享 schema、目录结构和策略。
- `agent-global-context-recall`：在工作前或工作中读取相关全局上下文。
- `agent-global-context-capture`：观察强信号，只把候选写入 staging。
- `agent-global-context-review`：审查、提升、拒绝、过期和清理候选。
- `agent-global-context-commit`：写入已确认长期上下文和 session 摘要。

在 v2 Recall/Skill Adapter 完成前，这五个 Skills 继续作为当前兼容层工作。本阶段保持既有候选流程，不会因为 Runtime 代码存在就静默启用 Codex 采集或迁移 v1 数据。

## 候选流程

```text
auto capture
  -> staging/inbox.md 或 staging/pending-review.md
  -> review
  -> commit
  -> long-term memory
```

候选不是事实。除非用户要求 review，或候选与当前任务直接相关，否则候选不进入默认 recall。

## 仓库结构

```text
skills/
  agent-global-context/
    references/
  agent-global-context-recall/
  agent-global-context-commit/
  agent-global-context-capture/
  agent-global-context-review/

templates/
  memory/
    config.yaml
    index.md
    user/
    environment/
    projects/
    staging/

docs/
  architecture.md
  architecture.en.md
  architecture.zh.md
  design.md
  design.en.md
  design.zh.md
  install.md
  examples.md
  full-flow-example.md
```

## 默认 Memory Root

```text
~/.agent-global-context/
```

Windows：

```text
C:\Users\<user>\.agent-global-context\
```

## 文档

- [架构](docs/architecture.md)
- [设计](docs/design.md)
- [Agent Global Context v2 已确认设计](docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md)
- [安装](docs/install.md)
- [示例](docs/examples.md)
- [完整流程示例](docs/full-flow-example.md)

## 状态

v2 Runtime Foundation 已在仓库中实现。五个 alpha Skills 在 Adapter 阶段继续生效；Codex 旁路采集和 v1 迁移已经完成设计，但尚未激活。
