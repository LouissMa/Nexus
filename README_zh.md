# Nexus / LifeAgent：你的个人 AI 管家

> **一个具备长期记忆、规划、复盘和受控执行能力的主动型、本地优先个人 AI 助手。**

Nexus 会记住目标和生活上下文，生成每日计划，按时运行简报与复盘，协调有明确边界的专职 Agent，并且只连接你显式授权的工具。

[English](./README.md) | [中文](./README_zh.md)

---

## 项目定位

大多数助手会等待用户提问。Nexus 的目标是成为一个可靠的个人 AI 核心，在合适的时间记忆、规划、提醒、复盘，并执行已经命名和授权的动作。

长期方向是构建由 CLI、网页、语音和未来具身接口共享的 Personal AI Operating System。当前版本不是 AGI，而是一个本地运行、权限边界明确的个人助手。

## 当前功能

- 长期记忆：搜索、语义 RAG、Qdrant 持久化、Re-index、生命周期、隐私、过期、压缩和可解释重排。
- 目标与复盘：目标、打卡、静默目标检测、持久化每日任务、阻碍、未解决事项、晚间复盘和四种 Coach 模式。
- 习惯追踪：每日/指定星期周期、同日幂等打卡、连续完成天数、完成率和归档。
- 项目追踪：关联目标与任务、里程碑、推导或显式进度、纠正历史和归档。
- 可解释离线建议：从静默目标、阻塞/待办任务、习惯风险和里程碑期限生成，并提供过期快照与需批准的受限动作。
- 日历感知重排：基于只读实时 iCalendar 约束生成预览，按优先级分配、缩短或说明无法安排，并通过状态版本安全应用。
- 统一 `nexus ask` 入口：识别常用中英文本地意图，写操作先预览并批准，习惯打卡可低风险执行，并可选用严格 JSON 的 LLM 意图选择。
- 可选 OpenAI-compatible LLM 生成，本地保存 Provider 与模型层级，并对配置脱敏。
- 只读天气、iCalendar、Todoist、GitHub、Notion、IMAP 邮件头和受目录约束的文件系统集成。
- 基于 stdio 或 Streamable HTTP 的 MCP Client，支持 Schema 发现、deny/ask/allow、有限重试和安全审计。
- 有预算与降级机制的 Memory、Tool、Planner、Reflection、Coach Agent 协作，以及隐私安全轨迹。
- 按用户 IANA 时区主动运行早晨简报、晚间复盘和静默目标提醒。
- 持久化通知收件箱、可选控制台/Webhook 投递，以及普通或跨夜免打扰时段。
- 响应式 Loopback Dashboard：Today、Goals、Habits、Projects、Suggestions、Memory、Activity 和脱敏 Settings；六条精确的 CSRF 保护动作支持原子习惯增量打卡、进度、建议决策以及读取实时日历的重新规划预览/应用。
- 受权限控制的 Nexus stdio MCP Server：七个有界只读工具、五个默认需要批准的写工具、逐工具 deny/ask/allow 策略覆盖，以及不记录用户原文和秘密的摘要审计。
- 受策略控制的命名自动化：固定网页、固定命令、GitHub 检查和 Markdown 状态报告。

## 快速开始

安装核心包并创建本地用户配置：

```bash
python -m pip install -e .
nexus config profile set --name Alex --timezone Asia/Shanghai
nexus config profile show
```

添加上下文并创建今日计划：

```bash
nexus memory add "Alex 正在准备 IELTS。" --tags 学习 考试
nexus goal add "IELTS 听力" --description "完成一次专注训练" --cadence-days 1
nexus plan day --name Alex --coach-mode academic
nexus task list
nexus briefing --name Alex --weather "天气晴，最高 25 C"
nexus review day --name Alex
```

这些本地流程不需要 API key。

## 记忆、工具、MCP 与 Agent

按需安装本地语义检索和工具依赖：

```bash
python -m pip install -e ".[rag,tools,mcp]"
nexus config embedding set --provider fastembed --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
nexus memory reindex
nexus memory retrieve "考试准备" --limit 5
```

FastEmbed 和本地 Qdrant 不需要 API key。托管 Embedding 和远程服务需要各自的凭据。

只配置你希望使用的只读集成：

```bash
nexus config tool set weather --location "Shanghai"
nexus config tool set github --repo "example/project"
nexus config tool set filesystem --root "/path/to/project"
nexus config tool show
nexus briefing --name Alex --live-tools
nexus tool audit --limit 20
```

配置 MCP Server，并显式批准工具：

```bash
nexus config mcp add research --transport stdio --command python --arg path/to/server.py
nexus mcp tools research
nexus config mcp policy research search ask
nexus mcp call research search --arguments '{"query":"科研笔记"}' --approve
nexus mcp audit --limit 20
```

Agent 模式保持可选且有明确预算：

```bash
nexus plan day --agents --coach-mode startup
nexus review day --agents --coach-mode academic
nexus briefing --agents --live-tools
nexus agent runs --limit 10
```

Tool Agent 只能自主选择已经启用且策略明确为 `allow` 的 MCP 工具。专职 Agent 失败时会降级到本地流程。

通过本地 stdio 将 Nexus 自身暴露给兼容 MCP 的客户端：

```bash
pip install -e ".[mcp]"
nexus mcp-server stdio
# 仅为当前进程批准一个 ask 策略写工具：
nexus mcp-server stdio --approve-tool nexus_check_in_habit
```

Server 将目标、记忆检索、习惯、项目、建议和每日任务作为有界只读工具提供。习惯打卡、项目进度和建议接受默认采用 `ask`；只有通过 `--approve-tool` 命名批准，或在 `.nexus/config.local.json` 的 `nexus_mcp_server.tool_policies` 中配置为 `allow` 时才会执行。

## 主动运行时、Dashboard 与自动化

Runtime Job 默认关闭，只有显式配置后才会运行。配置三个任务、本地时间和免打扰时段：

```bash
nexus config runtime set \
  --job morning_briefing \
  --job evening_review \
  --job stale_goal_reminders \
  --morning-time 08:00 \
  --evening-time 21:30 \
  --reminder-time 12:00 \
  --quiet-hours 23:00 07:00 \
  --console
nexus config runtime show
```

可选的 `--use-llm`、`--live-tools` 和 `--agents` 开关会让定时任务复用已经配置好的 Provider、工具权限和 Agent 流程。

查看或运行调度器：

```bash
nexus runtime status
nexus runtime tick
nexus runtime run morning_briefing
nexus runtime run evening_review
nexus runtime run stale_goal_reminders
nexus runtime start
```

普通定时任务会在执行前按 `job + 本地日期` 占用当日执行权，重启后不会重复发送。`runtime run` 是显式手动执行和重试入口。

每条消息都会先写入本地收件箱，再尝试控制台或 Webhook 投递。免打扰时段只延后非紧急外部投递，不会丢失收件箱记录。

```bash
nexus notifications list --limit 20
nexus notifications flush
```

查看隐私过滤后的 Snapshot，或启动 Dashboard：

```bash
nexus dashboard snapshot
nexus dashboard serve
# 打开 http://127.0.0.1:8765
```

Dashboard 现在包含八个视图。Today 展示日程、任务、提醒和最近的简报/复盘；Habits 可以打卡，Projects 可以进行带修正保护的进度更新，Suggestions 可以接受/忽略建议，Today 还提供重新规划预览/应用。Goals、可检索记忆、受限活动摘要和脱敏配置继续采用隐私过滤。

自动化以命名 JSON Definition 保存。新 Definition 默认使用 `ask`，运行时必须传入一次性的 `--approve`。

```bash
nexus automation set project-home --definition '{"type":"browser","url":"https://github.com/example/project","allowed_hosts":["github.com"],"policy":"ask"}'
nexus automation set repo-check --definition '{"type":"github_inspect","repo":"example/project","limit":20,"policy":"ask"}'
nexus automation set git-status --definition '{"type":"command","argv":["git","status","--short"],"cwd":".","allowed_roots":["."],"timeout_seconds":30,"max_output_bytes":65536,"policy":"ask"}'
nexus automation set status-report --definition '{"type":"status_report","output_path":"./nexus-status.md","allowed_roots":["."],"policy":"ask"}'
nexus automation list
nexus automation run project-home --approve
nexus automation run status-report --approve
nexus automation audit --limit 20
nexus automation remove project-home
```

支持的类型是 `browser`、`command`、`github_inspect` 和 `status_report`。Definition 在配置时固定，调用者不能在运行时追加任意参数或替换目标。

## API Key 与本地配置

本地记忆、目标、规划、任务更新、打卡、确定性简报/复盘、主动调度、通知收件箱、Dashboard、本地稀疏检索、FastEmbed、确定性报告和本地网页/命令自动化都不需要 API key。

只有选择需要访问外部 Provider 的功能时才需要凭据：

- LLM 生成，包括配置了 `--use-llm` 的定时任务。
- 托管 Embedding Endpoint 或远程 Qdrant。
- 需要身份认证的外部集成，例如 Todoist、私有 GitHub、Notion、IMAP 或私有日历订阅。Open-Meteo 和公开 GitHub 访问可以不使用凭据。
- 需要身份认证的远程 MCP Server。

LLM 配置示例：

```bash
nexus config llm set --provider custom --base-url "https://provider.example/v1" --api-key "<api-key>" --simple-model "<fast-model>" --complex-model "<strong-model>"
nexus config llm show
nexus briefing --llm --model-tier simple
```

本地配置保存在 `.nexus/config.local.json`。CLI 和 Dashboard 会隐藏秘密。不要提交整个 `.nexus/` 目录。

## 安全边界与当前限制

- `.nexus/` 保存个人状态、凭据、向量、运行历史、通知、审计、轨迹、模型和锁文件；Git 会整体忽略该目录。
- 共享配置更新使用操作系统级跨进程事务锁，校验本次更新的配置 Section，保留无关 Section，并通过原子替换写入。
- 状态保存和通知投递状态转换同样使用规范化的操作系统级锁。多个进程不会覆盖调度认领，也不会同时认领同一条延迟通知；超长损坏通知行会被跳过，并在重写时移除。
- Dashboard 只允许 Loopback 地址。它验证 `Host`、`Origin` 和每进程 CSRF Token，只提供精确读取路由和六条白名单动作路由，拒绝编码别名、目录穿越和通用写接口，限制输入/输出，并按 Section 隔离错误。
- Nexus MCP Server 仅支持显式启动的 stdio。固定的 12 个工具覆盖今日上下文、记忆检索、目标、习惯、项目、建议、重新规划预览，以及添加记忆/目标、习惯打卡、项目进度和已验证的重新规划应用。只读工具和参数/结果都有边界；写工具默认采用 `ask`；审计不会记录用户原文和秘密。
- 自动化策略为 `deny`、`ask` 和 `allow`。`ask` 每次都需要一次性批准；无人值守执行必须使用 `allow`。
- 浏览器自动化只能打开固定 HTTP(S) URL，并且必须配置非空、匹配的 Host Allowlist。
- 命令自动化使用固定参数数组和 `shell=False`。工作目录和报告路径必须位于显式存在的 Root 内；执行时间和捕获输出都有上限。
- 通知与自动化 Payload 有明确边界；工具、MCP、Agent 和自动化记录会脱敏，Dashboard 只公开有界的最近摘要；损坏的 JSONL 行会被跳过。
- Nexus 当前不提供开放式自主运行、远程 Dashboard、浏览器任意写操作、LLM 任意生成命令、语音/视觉、智能家居控制或机器人能力。

## CLI 命令地图

```bash
nexus memory add|list|show|search|retrieve|update|relate|archive|restore|forget|purge|compress|maintain|reindex|index-status
nexus goal add|list|check-in
nexus habit add|list|check-in|archive
nexus project add|list|milestone-add|milestone-update|progress|archive
nexus suggestion list|refresh|accept|dismiss
nexus replan preview|apply
nexus ask TEXT [--approve] [--llm] [--show-intent]
nexus plan day
nexus task list|update
nexus review
nexus review day
nexus briefing
nexus tool weather|calendar|todo|github|notion|email|files|audit
nexus mcp servers|tools|call|audit
nexus mcp-server stdio [--approve-tool NAME]
nexus agent runs|show

nexus config llm set|show
nexus config embedding set|show
nexus config tool set|disable|show
nexus config mcp add|disable|remove|policy|planning-tool|show
nexus config profile show|set
nexus config runtime show|set

nexus runtime status|tick|run|start
nexus notifications list|flush
nexus dashboard snapshot|serve
nexus automation list|set|run|remove|audit
```

使用 `nexus <command> --help` 查看准确参数。

## 项目文档

- [架构文档](./docs/architecture.md)
- [路线图](./docs/roadmap.md)
- [AIOS 任务清单](./docs/aios_task_checklist.md)
- [项目文件职责清单](./docs/file_inventory.md)
- [产品愿景](./docs/product_vision.md)

## 开发维护

```bash
python -m pytest tests -q
python -m ruff check src tests
python -m ruff format --check src tests
```

用户可见能力或重要文件发生变化时，要同步更新两份 README、任务清单和文件职责清单。不要提交 Key 或本地 Runtime 数据。

## 路线概览

Phase 1-11 已完成：CLI 基础、可选 LLM、RAG 2.0、Planning/Reflection、真实只读集成、MCP 客户端与 Nexus MCP Server、有边界的多 Agent 协作、高级记忆生命周期、主动 Runtime、交互式生活 Dashboard、受权限控制的命名自动化、习惯、项目、建议、自适应重新规划和统一对话入口。

下一步可以深化 Calendar/RAG 驱动的建议和科研伙伴工作流。语音、视觉、智能家居与机器人接口仍是长期方向，并且必须复用同一套权限和审计边界。
