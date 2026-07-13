# Nexus / LifeAgent：你的个人 AI 管家

> **一个具备长期记忆、规划和复盘能力的主动型个人 AI 助手。**

Nexus 是一个开源、本地优先的个人 AI 助手。它会记住目标、检索相关上下文、生成每日计划，并帮助用户复盘和采取行动。

[English](./README.md) | [中文](./README_zh.md)

---

## 项目定位

大多数 AI 助手都是被动的：用户提问，它才回答。

Nexus 不同：它的目标是记忆、规划、提醒、复盘，并在获得授权后通过工具执行任务。

当前项目首先专注于构建可靠的个人助手核心：记忆、目标、规划、复盘和可选的 LLM 生成。

长期来看，这个核心可以发展成由 CLI、网页、语音和视觉界面共享的 **Personal AI Operating System**。在明确授权和安全边界下，未来可以连接数字工具、家庭设备和机器人系统。这些是长期方向，不是当前已经实现的能力。

## 当前功能

- **记忆系统**：添加、列出、关键词搜索、RAG 检索长期记忆。
- **RAG 长期记忆**：保存本地 sparse embedding，并在简报中检索相关记忆。
- **目标追踪**：添加目标，设置描述和检查周期。
- **目标打卡**：记录目标进展。
- **主动复盘**：发现长期未推进的目标并生成提醒。
- **每日规划**：把活跃的长期目标拆解为今天可执行、可持久化的优先任务。
- **结构化任务追踪**：更新任务状态、阻碍、未解决事项和进展备注。
- **晚间复盘 / Reflection**：汇总今日推进、任务结果、阻碍、RAG 记忆和明日优先事项。
- **Coach 模式**：规划和复盘支持严格、温柔、学术、创业四种模式。
- **早晨简报**：根据目标、提醒、天气文本和记忆生成模板简报。
- **LLM 智能简报**：可选调用 OpenAI-compatible LLM 生成更自然的简报。
- **LLM Provider 配置**：本地保存 provider、模型和 simple/complex 模型层级。
- **Prompt 查看**：使用 `--show-prompt` 查看 LLM 上下文。
- **本地存储**：默认保存到 `.nexus/state.json`。

## 快速开始

```bash
python -m pip install -e .

nexus memory add "Louis 正在准备 IELTS，并计划申请海外 CS/AI 硕士。" --tags 身份 学习
nexus memory add "Louis 正在开发 Nexus，希望把它做成个人 AI 管家。" --tags 项目 Nexus
nexus goal add "IELTS 听力训练" --description "完成一次专注听力训练" --cadence-days 1
nexus goal add "开发 Nexus" --description "完成早晨简报模块" --cadence-days 2
nexus briefing --name Louis --weather "天气晴，最高 25 C"
```

## RAG 长期记忆

当前 RAG MVP 是本地实现，不需要外部 embedding API。

```bash
nexus memory retrieve "IELTS listening practice" --limit 3
nexus briefing --llm --show-prompt --name Louis
```

它会做这些事：

- `nexus memory add` 会保存一个本地 deterministic sparse embedding。
- `nexus memory retrieve` 会返回相关记忆和 `retrieval_score`。
- `nexus briefing` 会根据目标、提醒、天气文本和用户上下文构造检索 query。
- 如果没有检索到相关记忆，会退回最近记忆 fallback。

当前完成的是本地 RAG MVP，并不是生产级向量 RAG。真实神经网络 embedding 模型、向量数据库持久化、重新索引、记忆重要性评分和长期记忆压缩仍是后续工作。

## 每日规划与复盘

根据活跃的长期目标生成今日计划：

```bash
nexus plan day --name Louis --coach-mode academic
nexus plan day --llm --model-tier complex --show-prompt
```

当天第一次运行会生成最多三个优先任务，并保存到 `.nexus/state.json`。同一天重复运行会返回原有任务，不会重复创建。

追踪执行状态和复盘信息：

```bash
nexus task list
nexus task update <task_id> --status in_progress --note "开始第一组练习"
nexus task update <task_id> --blocker "需要日历权限" --unresolved "明天重新安排此任务"
nexus task update <task_id> --status completed
nexus review day --name Louis --coach-mode strict
```

填写 `--blocker` 后，任务会自动变为 `blocked`。晚间复盘会把阻塞任务和未解决事项放入明日优先级。Coach 模式包括 `strict`、`gentle`、`academic` 和 `startup`。

## LLM 使用说明

普通本地功能不需要 API key：记忆、目标、每日规划、任务更新、打卡、主动/晚间复盘、模板简报和本地 RAG 检索都可以直接运行。

只有使用 LLM 功能时才需要 API key，例如：

```bash
nexus briefing --llm
```

不要把 API key 提交到 GitHub。

## 本地 LLM 配置

为了方便测试项目，可以把 provider 和模型设置保存到本地：

```bash
nexus config llm set --provider deepseek --api-key "你的 key" --simple-model v4flash --complex-model v4pro --default-tier simple
nexus config llm show
```

配置文件默认保存到：

```text
.nexus/config.local.json
```

这个文件已经被 Git 忽略。CLI 输出时 API key 会自动脱敏。

模型层级建议：

- `simple`：便宜、快，适合简报、短总结、简单建议。
- `complex`：更强，适合规划、深度复盘、架构/代码分析、多 Agent 决策。

```bash
nexus briefing --llm --model-tier simple
nexus briefing --llm --model-tier complex
```

## CLI 命令

```bash
nexus memory add "..." --tags 学习 项目
nexus memory list
nexus memory search IELTS
nexus memory retrieve "IELTS listening practice" --limit 5

nexus goal add "开发 Nexus" --description "完成 MVP 功能" --cadence-days 2
nexus goal list
nexus goal check-in <goal_id> "完成了今天的训练。"

nexus plan day --name Louis --coach-mode academic
nexus task list
nexus task update <task_id> --status completed

nexus review
nexus review day --name Louis
nexus review day --llm --show-prompt --name Louis
nexus briefing --name Louis --weather "天气晴，最高 25 C"
nexus briefing --llm --show-prompt --name Louis

nexus config llm set --provider deepseek --api-key "你的 key" --simple-model v4flash --complex-model v4pro
nexus config llm show
```

## 项目跟踪

- [AIOS 任务清单](./docs/aios_task_checklist.md)：跟踪 Nexus 距离 J.A.R.V.I.S.-like AIOS 还差什么。
- [项目文件职责清单](./docs/file_inventory.md)：说明重要文件的职责。
- [架构文档](./docs/architecture.md)：当前系统设计和未来架构。
- [路线图](./docs/roadmap.md)：开发阶段和状态。

## 开发维护流程

每次实现新功能时：

1. 更新相关代码和测试。
2. 如果是用户可见功能，同步更新 `README.md` 和 `README_zh.md`。
3. 如果进度变化，更新 `docs/aios_task_checklist.md`。
4. 如果新增重要文件或文件职责变化，更新 `docs/file_inventory.md`。
5. 尽可能先跑测试再提交。
6. 除非用户明确要求推送，否则完成后询问是否推送。
7. 永远不要提交 API key 或 `.nexus/config.local.json`。

## 路线概览

- **Phase 1**：CLI MVP：记忆、目标、打卡、主动复盘、早晨简报。已完成。
- **Phase 2**：LLM 智能简报和 Provider 配置。已完成。
- **Phase 3**：本地 RAG 长期记忆 MVP。已完成。
- **Phase 4**：持久化每日规划、Reflection 与 Coach 模式。已完成。
- **下一步**：RAG 2.0，包括真实 Embedding、向量数据库持久化和 Re-index。
- **然后**：真实工具集成、MCP 工具调用和权限模型。
- **之后**：多 Agent 协作、高级记忆重要性/压缩、主动触发系统和 Dashboard。
- **长期方向**：在同一个 Nexus 核心上增加语音、视觉、智能家居适配器和可选的机器人集成。
