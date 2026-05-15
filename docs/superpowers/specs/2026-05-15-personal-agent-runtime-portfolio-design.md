# Personal Agent Runtime Portfolio Design

## Purpose

Build a single-page personal portfolio website for Wenfeng Xie that presents him as an **Agent Runtime & Backend Systems Engineer**.

The page should not read like a generic Java resume or an AI prompt portfolio. It should show a coherent technical identity:

> Building agent runtimes, workflow skills, memory/context systems, RAG foundations, and backend infrastructure that turn LLMs into reliable tools for real work.

## Audience

Primary readers:

- AI agent / platform teams evaluating agent engineering ability.
- Backend engineering teams interested in LLM workflow integration.
- Technical collaborators who may discover the work through GitHub, CSDN, or project links.
- Recruiters who need a clear technical story but may not know the internal project history.

Secondary readers:

- Developers interested in Codex skills, AI workflow automation, Java backend systems, MQTT, Netty, or observability.

## Positioning

Primary title:

```text
Agent Runtime & Backend Systems Engineer
```

Chinese headline:

```text
我构建 Agent Runtime，把 LLM 变成能处理真实工作的系统。
```

English support line:

```text
I build agent runtimes that connect LLMs, skills, memory, workflows, and backend systems into reliable tools for real work.
```

Core positioning:

```text
围绕 LLM 构建 Skills、Memory、RAG、Workflow Automation、Eval Loop 与 Java 后端基础设施。
```

## Core Narrative

The website should connect three threads into one story:

1. Long-term Java backend and distributed systems foundation.
2. Recent agent runtime, skill, memory, workflow, and evaluation projects.
3. Public writing that explains both backend systems and AI agent engineering.

The main argument:

> The author is not only using AI tools. He is turning implicit human workflows and engineering judgment into reusable, correctable, observable agent capabilities.

## Page Structure

### 1. Hero

Purpose: explain the identity within the first viewport.

Content:

- Name: `谢文锋 / Wenfeng Xie`
- Role: `Agent Runtime & Backend Systems Engineer`
- Main headline: `我构建 Agent Runtime，把 LLM 变成能处理真实工作的系统。`
- Supporting copy:

```text
我长期关注 Java 后端、分布式、高并发、MQTT、Netty、Kafka 和可观测性。
现在我把这些工程能力迁移到 AI Agent 方向，构建 Skills、Memory、RAG、Workflow Automation 和 Eval Loop，让 LLM 不只会回答，而是能在真实项目、真实浏览器和真实工作流中可靠执行。
```

Tags:

```text
LLM Runtime
Skills
Memory
RAG
Workflow Automation
Java Backend
Observability
```

Primary actions:

- View Projects
- Read Articles
- GitHub
- CSDN

Visual direction:

Use a compact architecture diagram, not decorative AI imagery:

```text
LLM
 + Skills
 + Memory
 + RAG
 + Workflow
 + Tools
 + Eval
 + Backend Systems
 = Reliable Agent Runtime
```

### 2. What I Build

Purpose: summarize the capability map.

Four cards:

1. **Agent Skills & Thinking Runtime**
   - Thinking Skills
   - intent routing
   - domain skills
   - no-skill boundary
   - conversation review
   - benchmark loop

2. **Memory / Context / RAG Runtime**
   - Agent Global Context
   - P0-P4 memory
   - recall / capture / review / commit
   - context builder
   - selective memory rather than full transcript

3. **Browser-backed Workflow Automation**
   - Codex Chrome Workflow Skill
   - Excel to OA workflow
   - real Chrome login session
   - duplicate-date checks
   - human confirmation boundary
   - correction to reusable rule

4. **Backend Systems Foundation**
   - Java / Spring Boot
   - Netty / EventLoop / Pipeline
   - MQTT / mqtt-plus
   - Kafka / distributed events
   - OpenTelemetry / SkyWalking
   - Redis / rate limiting / caching

Closing line:

```text
共同模式：把人类隐性的工作规则，沉淀成可复用、可纠正、可验证的 Agent 能力。
```

### 3. Featured Agent Systems

Purpose: show project depth.

Project cards:

#### Thinking Skills

Description:

```text
一个领域中立的 AI thinking skill framework。它通过 thinking-router 判断请求意图，再进入写作、技术分析、学习、情绪支持、对话复盘等不同 thinking mode。
```

Highlights:

- intent routing
- domain-specific skills
- conversation-review / Dolores mode
- skill-evaluator
- benchmark-assistant
- failure case -> eval -> patch loop

Summary:

```text
把“AI 应该怎么想”从隐式 prompt 变成可观察、可评测、可进化的系统。
```

#### Agent Global Context

Description:

```text
一个 Markdown-first 的 agent 长期上下文系统，用 P0-P4 优先级管理用户背景、技术偏好、编码习惯、项目环境和临时任务状态。
```

Highlights:

- selective memory
- candidate staging before commit
- recall by priority and relevance
- sensitive and conflict-aware memory rules

Summary:

```text
让 agent 跨 session 保持连续性，同时避免记忆污染。
```

#### Project Coding Skills

Description:

```text
一组项目级 AI coding skills，帮助 coding agent 在开发前读取当前项目自己的 docs/ai-coding、架构规则、模块边界和历史上下文。
```

Highlights:

- source code as source of truth
- project-local AI context
- scoped module context
- develop:init / develop:feature workflow

Summary:

```text
让 coding agent 不再把一个项目的规则误用到另一个项目。
```

#### Learning Companion Skills

Description:

```text
一个长期学习 companion skill，把学习计划变成 dashboard、map 和 log，追踪 plan progress 与 effective progress。
```

Highlights:

- one dashboard per plan
- daily low-friction protocol
- close-out review
- mastery score
- rescue task

Summary:

```text
把学习从散落的聊天记录变成可持续跟踪的 agent workflow。
```

#### Codex Chrome Workflow Skill

Description:

```text
一个基于真实 Chrome 登录态的企业工作流自动化 skill，从 Excel 工作计划提取任务，进入 OA 页面创建任务、登记工时、检查重复日期，并在高风险动作前请求确认。
```

Highlights:

- real Chrome session
- Excel -> OA task/work-hour workflow
- duplicate-date checks
- missing date backfill confirmation
- correction -> reusable rule

Summary:

```text
把重复企业后台操作，从“人工记忆和点击”重构成可复用的 agent workflow。
```

### 4. Backend Foundation

Purpose: prove this is not only prompt or tool usage.

Intro:

```text
我不是只在 prompt 层做 AI。我长期关注后端系统如何组织复杂性：线程模型、事件循环、消息链路、协议边界、缓存、分布式事件、可观测性和测试。
```

Groups:

#### High-Concurrency & Network

Keywords:

```text
Netty / EventLoop / Pipeline / Java NIO / epoll / zero-copy / WebFlux / Nginx
```

Representative articles:

- Netty 不只是 TCP 框架：它解决的是高并发业务系统的组织问题
- Netty 线程模型源码分析：BossGroup、WorkerGroup 和 EventLoop
- Netty Pipeline 源码分析：从 IO 事件到业务 Handler 的责任链
- WebFlux 不是银弹：从阻塞 IO 到 epoll
- 零拷贝不是没有拷贝

#### IoT & MQTT Framework

Keywords:

```text
MQTT / Spring Boot / mqtt-plus / multi-broker / dynamic subscription / listener runtime
```

Representative articles:

- mqtt-plus 架构解析（一）：分层架构与设计哲学
- 一条 MQTT 消息如何到达你的 @MqttListener
- 多 Broker 管理，如何让一个应用同时连接多个 MQTT 服务
- 动态订阅与重连恢复
- 从内部项目到开源框架，mqtt-plus 的抽取过程与决策

#### Distributed Systems

Keywords:

```text
Kafka / distributed events / Redis rate limiter / idempotency / batching / cache index
```

Representative articles:

- 夯实 Kafka 系列
- 基于 Kafka 分布式事件框架 eval-event
- 自定义注解 @EvalEventListener 开发
- 分布式限流器框架 eval-rate-limiter
- 用去重 + 批处理扛住重复上报和数据库压力

#### Observability

Keywords:

```text
OpenTelemetry / SkyWalking Agent / trace / metrics / logs / agent usage tracking
```

Representative articles:

- OpenTelemetry 和 SkyWalking Agent 怎么选？
- 开源一个 Codex Token 用量统计 Skill

### 5. Case Studies

Purpose: turn projects into stories with problem, approach, and result.

#### Case Study 1: Thinking Skills

Problem:

```text
LLM 在面对模糊请求时，容易默认进入某种单一模式，比如把所有问题都当成编码任务。
```

Approach:

```text
设计 thinking-router，把请求先路由到合适的 thinking mode，再由领域 skill 接管回答方式。通过 conversation-review 和 skill-evaluator，把失败沉淀成 eval 和最小 patch。
```

Result:

```text
形成一个包含 routing、domain skills、review、benchmark、failure loop 的 agent thinking framework。
```

#### Case Study 2: Codex Chrome Workflow

Problem:

```text
企业 OA 工时系统没有开放 API，流程依赖真实 Chrome 登录态，且包含大量隐性人工判断。
```

Approach:

```text
设计 codex-chrome-workflow-skill：从 Excel 提取任务，进入真实 OA 页面，按规则创建任务和登记工时，对缺失日期和高风险操作请求确认。
```

Result:

```text
把重复后台操作变成可复用、可纠正、可审计的 agent workflow。
```

#### Case Study 3: mqtt-plus

Problem:

```text
Spring Boot 项目接入 MQTT 时，常见 demo 只解决“能连上”，但缺少完整的监听、发布、多 broker、序列化、错误处理和测试体系。
```

Approach:

```text
从真实项目中抽取 mqtt-plus，设计 core、starter、listener registry、message router、payload serializer、embedded broker 等模块。
```

Result:

```text
形成一个面向 Spring Boot 的 MQTT 框架，并输出完整架构解析系列文章。
```

### 6. Writing

Purpose: show ongoing public thinking and writing.

Intro:

```text
我通过技术写作整理复杂系统的底层结构，关注“为什么这样设计”，而不只是“怎么用”。
```

Categories:

- AI Agent & Skills
- Java Backend & Network
- MQTT & IoT
- Distributed Systems
- Observability
- Engineering Practice

Each category should show 3-5 selected CSDN articles.

### 7. Current Focus

Purpose: show the current technical trajectory.

Content:

```text
我正在系统学习和构建 Agent Knowledge Runtime：一个围绕 LLM 的知识、记忆、上下文、工具工作流、评测和后端基础设施层。
```

Current modules:

- RAG / Knowledge Agent
- Agent Memory / Context Engineering
- Workflow Orchestration
- Eval / Observability
- Java Backend / Distributed Systems

Closing line:

```text
目标是把 agent 从“会回答”推进到“能在真实工作中可靠执行、可追踪、可改进”。
```

### 8. Contact

Content:

- GitHub: `huajiexiewenfeng`
- CSDN: `xiewenfeng520`
- Email: optional

Final line:

```text
我构建围绕 LLM 的系统：Skills、Memory、Workflow、后端基础设施和评测闭环。
```

## Visual Direction

The site should avoid generic "futuristic AI" imagery.

Preferred tone:

- engineering-focused
- clear
- calm
- structured
- portfolio-like, not marketing-heavy

Visual components:

- architecture diagrams
- project cards
- article clusters
- case-study flows
- compact tags
- restrained color palette

Suggested palette:

- background: light neutral or deep slate
- primary: blue/cyan
- accent: amber or green for workflow/eval labels
- avoid excessive purple gradients, decorative blobs, or purely atmospheric AI art

## Information Architecture

Final section order:

```text
Hero
-> What I Build
-> Featured Agent Systems
-> Backend Foundation
-> Case Studies
-> Writing
-> Current Focus
-> Contact
```

## Success Criteria

The finished page should make three things clear within one minute:

1. Wenfeng is not only a Java backend engineer and not only an AI tool user.
2. His differentiator is building agent runtime capabilities around LLMs: skills, memory, workflow, context, and eval.
3. His backend foundation makes this agent direction credible for real-world systems.

The page should also provide direct links to:

- GitHub repositories
- CSDN article categories or selected articles
- key case studies

## Non-Goals

- Do not make a generic resume page.
- Do not make a flashy AI landing page.
- Do not over-focus on model training, CUDA, or research topics.
- Do not hide the Java/backend foundation behind AI buzzwords.
- Do not present Codex usage as only coding automation; show it as workflow agent runtime extension.
