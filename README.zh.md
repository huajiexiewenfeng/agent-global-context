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

Runtime Core 可以独立运行，MCP 是可选的 Host Adapter。安装 Adapter 不会启用
Codex 任务采集或 backfill。

## 快速开始

1. 为仓库、当前 Skills、Codex 配置、Runtime 安装目录和 Memory Root 选择互不
   重叠的路径。升级 v1 时，建议使用
   `~/.agent-global-context-v2` 这样的并行 v2 Root。

2. 使用显式路径运行可重复执行的本地安装器。

```powershell
$repository = (Resolve-Path "D:\src\agent-global-context").Path
& "$repository\scripts\install-local.ps1" `
  -RepositoryRoot $repository `
  -SkillsRoot "$env:USERPROFILE\.agents\skills" `
  -CodexConfig "$env:USERPROFILE\.codex\config.toml" `
  -MemoryRoot "$env:USERPROFILE\.agent-global-context-v2" `
  -InstallRoot "$env:USERPROFILE\.agent-global-context-runtime"
```

3. 重启 Codex，并新建一个 task。

安装器最终只保留一个公开 `agent-global-context` Skill，并通过一个 MCP Server
注册且仅注册三个工具：`agc.read`、`agc.write` 和 `agc.admin`。被替换的当前
文件会进入唯一备份；安装器可安全重复执行。

安装器不会迁移 Memory，也不会启用 Codex 任务采集或 backfill。在后续显式、
经过验证的退役操作前，应把 v1 保持为只读回滚材料。

## 仓库结构

```text
skills/
  agent-global-context/
    references/

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

## Memory Root

```text
~/.agent-global-context-v2/
```

Windows：

```text
C:\Users\<user>\.agent-global-context-v2\
```

已有的 v1 `~/.agent-global-context` Root 应保持只读，作为回滚材料，直到后续
显式退役。

## 文档

- [架构](docs/architecture.md)
- [设计](docs/design.md)
- [Agent Global Context v2 已确认设计](docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md)
- [Skill–MCP–Runtime 架构模式复盘](docs/skill-mcp-runtime-pattern.md)
- [安装](docs/install.md)
- [示例](docs/examples.md)
- [完整流程示例](docs/full-flow-example.md)

## 状态

v2 Runtime、单一公开 Skill、三工具 MCP Adapter、确定性并行迁移支持和可重复
执行的本地安装器均已实现。安装器不会启用 Codex 旁路采集或 backfill。
