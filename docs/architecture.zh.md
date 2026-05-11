# Agent Global Context 架构

## 概览

Agent Global Context 是一个面向 AI Agent 的 Markdown-first 全局上下文层。它用于保存跨 session 的关键上下文，同时避免把记忆系统变成完整聊天记录归档。

系统建立在三个核心思想上：

1. **基于优先级的上下文**：不是所有记忆都有相同价值，也不是所有记忆都应该同频读取。
2. **人类可审计的存储**：长期上下文以 Markdown 条目保存，并带有少量元数据。
3. **基于 skill 的操作**：Agent 通过聚焦的 skill 来读取、写入，并在未来审查全局上下文。

架构有意保持轻量。MVP 只使用文件、目录和 skill 指令。数据库、向量搜索和后台服务都是未来可选扩展。

## 目标

- 跨 session 保存稳定的用户、技术、代码、环境和项目上下文。
- 帮助 agent 继续工作，而不是每次重新发现稳定事实。
- 保持记忆对人类可读、可编辑、可审查。
- 只加载相关记忆，避免上下文再次爆炸。
- 不绑定特定 agent 运行时，支持多种 agent。

## 非目标

- 保存每一条对话消息。
- 替代当前模型上下文窗口。
- 保存密钥、凭据或私钥。
- 在未经用户确认时保存敏感个人判断。
- 在 MVP 中要求数据库或向量索引。

## 系统组件

```text
agent-global-context/
  skills/
    agent-global-context/
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
```

### 核心策略 Skill

`agent-global-context` 是共享策略 skill。

它定义：

- memory root 位置
- 优先级模型
- memory item schema
- 目录结构
- 读取规则
- 写入规则
- 敏感记忆规则

当需要设计、配置、审计或修改全局上下文系统时使用它。

### Recall Skill

`agent-global-context-recall` 负责读取记忆。

它回答：

- 当前任务应该读取哪些 memory 文件？
- 应该只读取摘要，还是读取完整条目？
- 当前任务是项目任务、代码任务、环境任务，还是继续上次工作？

Recall 是选择性的。它从 `index.md` 开始，然后根据优先级和相关性读取文件。

### Commit Skill

`agent-global-context-commit` 负责写入记忆。

它处理：

- 明确的“记住这个”请求
- session 压缩
- 长期偏好更新
- 项目决策记录
- 当前任务状态更新

Commit 是保守的。每条长期记忆都应该包含元数据。`P0-P2` 条目必须包含 rationale；`P3-P4` 条目在能补充上下文时应包含 rationale。

### Capture Skill

`agent-global-context-capture` 实现 alpha 自动捕获。

自动捕获是 `observe` 阶段的实现。它识别可能有长期价值的信号，并把候选条目写入 `staging/inbox.md`。

自动捕获默认开启。它只产生候选，不产生长期记忆。任何进入长期记忆的条目仍必须经过 commit。

### Review Skill

`agent-global-context-review` 用于审查 staged candidates，并维护候选生命周期。

它应该帮助：

- 去重
- 归档过期 session 状态
- 解决矛盾
- 审查 pending 的敏感记忆
- 提升有价值的暂存记忆
- 让过期候选失效

## Memory Root

默认 memory root：

```text
~/.agent-global-context/
```

Windows 示例：

```text
C:\Users\<user>\.agent-global-context\
```

这个位置有意保持 agent-neutral。只要不同 AI coding agent 支持兼容的 skill 或 instruction 工作流，就可以共享同一份全局上下文。

## Memory 目录结构

```text
~/.agent-global-context/
  config.yaml
  index.md

  user/
    profile.md
    preferences.md
    coding-style.md

  environment/
    machine.md
    agent.md

  projects/
    <project-id>/
      overview.md
      engineering.md
      decisions.md
      active.md
      sessions/

  staging/
    inbox.md
    pending-review.md
    rejected.md
```

## 文件职责

`config.yaml` 控制行为配置，例如自动捕获、读取策略、写入策略和敏感记忆规则。

自动捕获默认开启。它可以在配置中关闭。

模板中存在 staging 文件，但它们不是 MVP 自动流程的一部分。只有在用户明确要求暂存记忆，或敏感/高影响上下文需要等待审查时才使用。

自动捕获配置使用：

```yaml
auto_capture:
  enabled: true
  categories:
    preferences: true
    corrections: true
    identity: true
    project_decisions: true
  retention_days: 14
  recall_inbox: false
review:
  session_start_notice: true
  prompt_when_pending_count_gte: 5
  prompt_when_oldest_pending_days_gte: 7
```

`index.md` 是读取入口。它维护项目映射、默认读取文件和活跃项目状态指针。

`user/profile.md` 保存 `P0` 用户背景和稳定身份级上下文。

`user/preferences.md` 保存 `P1` 技术、工具、架构和协作偏好。

`user/coding-style.md` 保存 `P2` 代码习惯、测试习惯、review 期望和实现风格。

`environment/machine.md` 保存 `P3` 操作系统、shell、路径、工具、权限和机器相关事实。

`environment/agent.md` 保存 `P3` agent 设置、skill 位置、插件和操作约束。

`projects/<project-id>/overview.md` 保存 `P3` 项目目标、领域、技术栈和架构概览。

`projects/<project-id>/engineering.md` 保存 `P3` 命令、依赖、目录结构和已知工程坑点。

`projects/<project-id>/decisions.md` 保存 `P3` 长期项目决策及原因。

`projects/<project-id>/active.md` 保存 `P4` 当前任务状态、下一步、阻塞点和最近 session。

`projects/<project-id>/sessions/` 保存带日期的 `P4` session 摘要。

`staging/inbox.md` 保存未来可能提升的候选记忆。

`staging/pending-review.md` 保存需要用户确认的敏感或高影响候选记忆。

`staging/rejected.md` 保存被拒绝的记忆和不应再次加入的反记忆。

## 优先级模型

| 优先级 | 含义 | 默认读取 |
| --- | --- | --- |
| `P0` | 用户背景和身份级上下文 | 重要工作默认读取摘要 |
| `P1` | 技术和协作偏好 | 规划、架构、工具选择时读取 |
| `P2` | 代码习惯和工程风格 | 编码、review、测试、重构时读取 |
| `P3` | 项目和环境知识 | cwd 或请求命中项目/环境时读取 |
| `P4` | 临时 session 状态 | 仅在继续上次工作时读取 |

这个优先级模型避免记忆变成一大团不可区分的上下文。

## 读取预算

优先级定义重要性，相关性定义是否读取，预算定义读取深度。

当多个优先级同时命中时，先读取摘要：

1. `index.md`
2. `P0` `Recall Summary`
3. 活跃项目的 `P3` summary
4. 直接相关的 `P1/P2` summary
5. 只有继续任务时才读取 `P4` active state 和最近 session

上下文紧张时，应先丢弃旧 `P4` session 细节，而不是丢弃活跃项目上下文或直接相关的用户偏好。

## Memory Item Schema

长期记忆使用 Markdown 条目：

```markdown
## memory-id

- type: preference
- priority: P1
- confidence: confirmed
- source: user_explicit
- scope: global
- status: active
- created_at: YYYY-MM-DD
- updated_at: YYYY-MM-DD

Memory content.

Rationale:
Why this should influence future agent behavior.
```

必填字段：

- `type`
- `priority`
- `confidence`
- `source`
- `scope`
- `status`
- `created_at`
- `updated_at`

长期记忆必须包含 `Rationale`。这会迫使每条记忆说明它未来为什么有价值。

实际使用中，`P0-P2` 必须包含 `Rationale`。`P3-P4` 如果价值已经能从项目命令、决策或任务状态中明显看出，则 `Rationale` 推荐但不强制。

## 置信度模型

使用四个 confidence 值：

- `confirmed`：用户明确陈述、批准，或要求 agent 记住。
- `observed`：由可靠本地证据支持，例如仓库文件、命令输出、配置或重复可见行为。
- `inferred`：agent 根据上下文推导，但没有直接确认。
- `tentative`：证据弱、有歧义，或可能只是临时状态。

不要把 agent 的猜测标记为 `confirmed`。

## Recall 流程

```text
User request
  -> 判断是否需要全局上下文
  -> 读取 config.yaml
  -> 读取 index.md
  -> 加载 P0 Recall Summary
  -> 分类任务类型
  -> 加载相关 P1/P2/P3/P4 文件
  -> 使用已加载上下文继续任务
```

任务分类：

- 规划或技术选择 -> 读取 `P1`
- 代码实现/review/测试 -> 读取 `P1` 和 `P2`
- 环境或命令工作 -> 读取环境 `P3`
- 项目相关工作 -> 读取匹配项目的 `P3`
- “继续”、“恢复”、“上次” -> 读取项目 `P4`

Recall 应优先读取 `Recall Summary`，再按需读取完整条目。

## 项目识别

项目级 recall 和写入都需要稳定的 `<project-id>`。

按以下顺序识别项目：

1. 使用用户确认过的显式项目绑定。
2. 用当前工作目录或用户提供的路径匹配 `index.md` 的 `Project Map`。
3. 如果位于 Git 仓库内，从 Git remote 仓库名生成候选 id。
4. 如果没有 Git remote，则从当前目录名生成候选 id。
5. 如果 project id 是新的或存在歧义，先询问用户，再创建或依赖项目记忆。

Project id 应使用小写 ASCII slug。将空格和下划线转为连字符，移除不支持字符，合并重复连字符，并去掉首尾连字符。

用户确认过的绑定是权威来源。Git remote 和目录名 slug 只是启发式规则，在 monorepo、fork、submodule 或多个 worktree 场景下可能不稳定。

示例：

```text
C:\Users\me\Documents\New Project 2 -> new-project-2
git@github.com:owner/Agent Global Context.git -> agent-global-context
```

## Commit 流程

```text
User asks to remember or compress
  -> 分类为 P0-P4
  -> 检查敏感策略
  -> 选择目标文件
  -> 读取已有目标文件
  -> 去重或更新已有条目
  -> 写入 Markdown memory item
  -> 如果读取行为发生变化，更新 index.md
  -> 报告变更文件
```

用户明确要求记住的信息，通常可以直接提交，除非内容敏感。

主动发现或推断出的候选记忆，应先进入 staging，除非配置允许直接提交且来源可靠。

## 去重和更新流程

追加 memory item 之前，应先扫描目标文件，寻找语义相同的已有条目。

当新信息符合以下情况时，应更新已有条目：

- 澄清同一个事实或偏好
- 改变 confidence 或 source
- 补充 rationale 或 scope
- 刷新 `updated_at`

只有当新信息代表独立的长期事实、偏好、习惯、决策或任务状态时，才追加新条目。

如果新信息替代旧信息，应将旧条目标记为 `status: superseded`，并在有用时给新条目添加 `supersedes`。不要用 inferred memory 静默覆盖 confirmed memory。

## 自动捕获流程

```text
Conversation signal
  -> 评估捕获触发规则
  -> 应用敏感过滤
  -> 写入 staging/inbox.md 或 pending-review.md
  -> 等待 review 或 commit
```

只捕获强信号：

- 用户偏好或习惯
- 长期项目或工作流决策
- 用户对 agent 行为的纠正
- 稳定身份级上下文，例如背景、角色、语言或工作环境

明确不捕获：

- 一次性任务细节
- 临时状态
- 尚未决定的探索性想法
- 闲聊或无关讨论
- 未确认的心理、人格、动机或情绪状态推断

候选条目应包含：

- `source`
- `proposed_priority`
- `proposed_confidence`
- `rationale`
- `created_at`
- `status`

自动捕获的 confidence 上限是 `observed`，默认是 `inferred`，弱证据使用 `tentative`。`confirmed` 必须来自用户显式动作。

敏感过滤必须在 observe 阶段生效。密钥和凭据不得进入 staging。个人敏感上下文只有在可能确实值得保存且询问用户时，才进入 pending review。未确认的心理或人格推断默认丢弃。

`staging/inbox.md` 不进入默认 recall。只有用户要求 review 候选，或候选与当前任务高度相关时才读取。即使读取，也不能把候选当作已确认的长期事实。

操作原则：

```text
自动捕获可以发现。
暂存区可以承载。
审查可以批准。
提交才能成为长期记忆。
读取时不能把未确认候选当事实。
```

## 候选审查流程

```text
staging candidate
  -> 审查 confidence 和敏感性
  -> promote、reject、expire 或继续 pending
  -> 如果 promoted，执行 commit 规则
  -> 写入正式 memory item
  -> 更新候选状态
```

提升规则：

- `confirmed`：可以提升。
- `observed`：来源可靠且非敏感时可以提升。
- `inferred`：需要用户确认。
- `tentative`：需要确认或重复证据。

候选被提升时，应记录：

```markdown
- status: promoted
- reviewed_at: YYYY-MM-DD
- promoted_to: path/to/file.md#memory-id
```

被拒绝和过期的候选也应记录 `reviewed_at` 和简短原因。

当以下情况出现时，agent 应提示 review：

- 待审候选数量达到配置阈值
- 最旧待审候选年龄达到配置阈值
- `pending-review.md` 中存在敏感/高影响候选
- commit 前发现候选与当前任务直接相关

Review 提示不应阻塞正常工作，除非确认或过期策略要求处理。

## 冲突解决

使用以下优先级：

1. 当前明确用户指令。
2. 安全和敏感记忆策略。
3. 活跃项目的项目级 `P3` 约束和决策。
4. 用户代码习惯 `P2`。
5. 用户技术偏好 `P1`。
6. 用户 profile 上下文 `P0`。
7. 临时 session 状态 `P4`。

在项目内，已确认的项目约定优先于通用个人偏好。如果这个冲突会影响决策，应简短说明。

## Session 压缩流程

```text
Session end or user request
  -> 总结目标、决策、当前状态、下一步
  -> 写入 sessions/YYYY-MM-DD-HHMM.md
  -> 更新 active.md
  -> 只提升有长期价值的 P0-P3 记忆
  -> 省略噪音细节
```

Session 摘要不是完整转录，而是未来恢复工作的锚点。

## 敏感记忆 Gate

敏感或高影响记忆不能被静默提交。

写入前需要确认：

- 真实姓名、联系方式、地址、账号
- 财务、医疗、家庭或私人关系信息
- 公司秘密或商业机密
- 心理、人格、动机或情绪状态推断

永远不要保存：

- 密码
- API key
- 私钥
- 认证 token
- 恢复码

如果用户要求保存密钥，agent 应说明这个 Markdown 记忆系统不适合作为密钥存储。

## 数据生命周期

```text
observe -> stage -> commit -> review -> archive/supersede/reject
```

MVP 支持：

- recall
- explicit commit
- session compression
- 只产生候选的自动捕获
- 候选审查和提升

alpha MVP 不支持自动写入长期记忆。候选提升仍必须执行 commit 规则。

未来生命周期支持：

- 定期清理
- 矛盾检测
- 记忆老化和归档

`P4` active state 应被视为临时状态。应原地更新 `active.md`，移除已完成的下一步，并避免把过期阻塞点带入无关工作。Session 摘要可以作为历史恢复点保留，但 recall 只应读取 `active.md` 引用的最近摘要，或配置允许的最近摘要。

## Agent-Neutral 设计

项目在以下位置避免使用特定 agent 名称：

- 仓库名
- memory root path
- skill 名称
- 文件名
- 文档

这让系统可以在不同 coding agent 之间迁移。

Agent 专属细节应该放在：

```text
environment/agent.md
```

或对应 agent 的安装文档中。

## 扩展点

### Search Layer

未来版本可以加入：

- 基于 ripgrep 的本地搜索
- SQLite 全文搜索
- 向量搜索
- 生成式索引文件

Markdown 文件应始终作为 source of truth。

## 失败模式

### 记忆污染

原因：提交太多信息，或提交弱推断。

缓解：

- 要求 rationale
- 使用 staging
- 标注 source 和 confidence
- 确认敏感或高影响记忆

### 上下文爆炸

原因：默认加载所有 memory 文件。

缓解：

- 从 `index.md` 开始
- 使用优先级读取
- 优先读取 `Recall Summary`
- 限制 session 历史加载

### 过期记忆

原因：旧偏好或旧项目状态仍保持 active。

缓解：

- 使用 `status`
- 支持 `review_after`
- 归档过时的 P4 状态
- 显式 supersede 旧决策

### Agent 绑定

原因：把某个 agent 运行时的假设写进核心系统。

缓解：

- 保持命名 agent-neutral
- 存储层只用 Markdown/YAML
- 把运行时细节放进安装文档

## MVP 边界

MVP 包含：

- 核心策略 skill
- recall skill
- commit skill
- capture skill
- review skill
- Markdown memory 模板
- 架构、安装和示例文档

MVP 不包含：

- CLI installer
- 数据库索引
- 向量搜索
- 后台自动化

## 成功标准

MVP 成功时，agent 应该能够：

1. 在不读取所有文件的情况下加载相关用户和项目上下文。
2. 带元数据和 rationale 写入用户偏好。
3. 把 session 压缩成项目恢复点。
4. 根据 `active.md` 和最近 session 摘要继续工作。
5. 默认避免保存敏感或低价值信息。
6. 可预测地识别项目上下文。
7. 优先更新已有记忆，而不是制造可避免的重复条目。
