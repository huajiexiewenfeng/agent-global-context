# Agent Global Context

[English](README.md) | 简体中文

面向 AI Agent 的 Markdown-first 全局上下文 skills。

Agent Global Context 帮助 coding agent 跨 session 保存关键用户身份、技术偏好、代码习惯、工作环境和项目知识。它不是完整聊天归档，而是一个选择性、可审计、会影响未来 agent 行为的全局上下文层。

## 为什么需要它

长对话最终会遇到上下文限制和压缩。常见做法是总结所有内容，但全量总结很快会变得嘈杂，也难以信任。

这个项目采用另一种方式：

- 只保存高价值上下文，不保存完整聊天记录。
- 使用 Markdown，让上下文可读、可编辑、可审查。
- 按优先级和任务相关性读取，而不是一次性加载所有内容。
- 自动捕获保持安全：候选先进入 staging，不直接进入长期记忆。
- 保持 agent-neutral：可用于 Codex、Claude Code、Cursor、OpenCode，以及其他支持 skills 或 instruction files 的 coding agent。

## 核心模型

Agent Global Context 使用五个优先级：

- `P0`：用户背景和身份级上下文
- `P1`：技术和协作偏好
- `P2`：代码习惯和工程风格
- `P3`：项目和工作环境知识
- `P4`：临时 session 状态

目标不是完美记忆，而是更好的连续性。

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

## Alpha MVP Skills

- `agent-global-context`：共享 schema、目录结构和策略。
- `agent-global-context-recall`：在工作前或工作中读取相关全局上下文。
- `agent-global-context-capture`：观察强信号，只把候选写入 staging。
- `agent-global-context-review`：审查、提升、拒绝、过期和清理候选。
- `agent-global-context-commit`：写入已确认长期上下文和 session 摘要。

自动捕获默认开启，但只写入 staging。长期记忆仍必须经过 review 和 commit。

## 候选流程

```text
auto capture
  -> staging/inbox.md 或 staging/pending-review.md
  -> review
  -> commit
  -> long-term memory
```

候选不是事实。除非用户要求 review，或候选与当前任务直接相关，否则候选不进入默认 recall。

## 相关学习工作流

这个 workspace 还配套使用本地 `learning-companion` 工作流来跟踪 Agent/RAG Knowledge Runtime 学习计划。它用 Markdown dashboard 和 log 保存每日学习状态，并通过“下课”收口复盘区分计划进度和有效掌握进度。

`learning-companion` 现在支持轻量老师模式，触发方式包括“你来教我学习”“继续学习”“我不明白”“换个例子”“老师模式”等。老师模式会围绕当天学习项小步讲解：先说明核心概念，再连接到用户的原始材料或项目，给一个具体例子，并只问一个检查问题。有效进度仍然只会在 `下课` 复盘后推进。

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
- [安装](docs/install.md)
- [示例](docs/examples.md)
- [完整流程示例](docs/full-flow-example.md)

## 状态

当前项目处于 alpha MVP 阶段。
