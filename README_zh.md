# Nexus / LifeAgent：你的个人 AI 管家

> **一个具备长期记忆、规划、复盘和受控执行能力的主动型、本地优先个人 AI 助手。**

Nexus 会记住目标和生活上下文，生成每日计划，按时运行简报与复盘，协调有明确边界的专职 Agent，并且只连接你显式授权的工具。

[English](./README.md) | [中文](./README_zh.md)

---

## 项目定位

Nexus 的目标是成为一个可靠的个人 AI 核心，理解目标、选择工具、执行真实任务、检查结果，并持续保留协作上下文。当前执行仍基于已注册意图和有边界的专用工作流。

长期方向是构建由 CLI、网页、语音和未来具身接口共享的 Personal AI Operating System。当前版本不是 AGI，而是一个本地运行、权限边界明确的个人助手。

下一优先阶段是 **Phase 15：通用任务执行核心**，依次建立工具契约与开源选型、
动态执行循环、任务持久化与审批恢复、共享上下文和成果验证。整个执行体系
尚未完整完成。15.1 已有工具契约，15.2 已增加 LangGraph 前台动态决策/执行循环；
15.3 已增加本地持久任务与审批恢复，15.4a 已接入显式选择的目标/RAG/研究上下文，15.4b 已接入文字/语音共享任务会话；15.5a 已增加预先声明的文件验收检查，完整目标语义验证和跨任务评估仍待实现。
详见[开发路线图](docs/roadmap.md)及
[当前能力、阶段里程碑与验收标准](docs/current_capabilities_and_next_phase.md)。

[15.5b 任务可靠性评估设计](docs/superpowers/specs/2026-09-20-execution-evaluation-design.md)已确认，
[实施计划](docs/superpowers/plans/2026-09-20-execution-evaluation.md)待审阅并选择执行方式。
范围包括离线安全回归、显式启用的真实模型评估与透明用量指标；文中的新命令尚未实现。

## 当前功能

- 长期记忆：搜索、语义 RAG、Qdrant 持久化、Re-index、生命周期、隐私、过期、压缩和可解释重排。
- 目标与复盘：目标、打卡、静默目标检测、持久化每日任务、阻碍、未解决事项、晚间复盘和四种 Coach 模式。
- 习惯追踪：每日/指定星期周期、同日幂等打卡、连续完成天数、完成率和归档。
- 项目追踪：关联目标与任务、里程碑、推导或显式进度、纠正历史和归档。
- Research Companion 2.0 研究伙伴：持久化研究项目，摄取 PDF/Markdown/TXT 全文，验证 Chunk 级引用，获取显式 HTTPS 网页，索引代码仓库，执行受限实验，并通过有预算的多 Agent 研究循环结合 RAG 生成带不确定性说明的结论。
- 可解释 Suggestions 2.0：综合静默目标、阻塞/待办任务、习惯风险、里程碑期限、实时日历冲突/专注窗口和任务相关 RAG 记忆，并提供过期快照与需批准的受限动作。
- 日历感知重排：基于只读实时 iCalendar 约束生成预览，按优先级分配、缩短或说明无法安排，并通过状态版本安全应用。
- 统一 `nexus ask` 入口：识别常用中英文本地意图，写操作先预览并批准，习惯打卡可低风险执行，并可选用严格 JSON 的 LLM 意图选择。
- 显式启动的本地 Voice Assistant MVP：有时长上限的按键说话录音、`faster-whisper` 转写、操作系统语音输出、统一对话路由和语音简报。
- Voice Assistant 2.0：WebRTC VAD 前台连续轮流会话、静默/轮数限制、退出短语和临时录音清理；尚无唤醒词与语音打断。
- Desktop Task Agent 基础版：通过文字或语音搜索文件名、批准后打开文档、启动已注册的 Windows 应用或网址，以及启动后列出今日任务。
- 可选 OpenAI-compatible LLM 生成，本地保存 Provider 与模型层级，并对配置脱敏。
- 只读天气、iCalendar、Todoist、GitHub、Notion、IMAP 邮件头、学术元数据和受目录约束的文件系统集成。
- 基于 stdio 或 Streamable HTTP 的 MCP Client，支持 Schema 发现、deny/ask/allow、有限重试和安全审计。
- 有预算与降级机制的 Memory、Tool、Planner、Reflection、Coach Agent 协作，以及隐私安全轨迹。
- 按用户 IANA 时区主动运行早晨简报、晚间复盘和静默目标提醒。
- 持久化通知收件箱、可选控制台/Webhook 投递，以及普通或跨夜免打扰时段。
- 响应式 Loopback Dashboard：Today、Goals、Habits、Projects、Research、Suggestions、Memory、Activity 和脱敏 Settings；六条精确的 CSRF 保护动作支持原子习惯增量打卡、进度、建议决策以及读取实时日历的重新规划预览/应用。
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

## 执行工具层（Phase 15.1）

```powershell
nexus executor tools
nexus executor call filesystem.read --arguments '{"path":"README.md","max_bytes":4000}'
nexus executor call automation.chatgpt --approve
```

需先配置文件系统授权目录或自动化别名。工具目录列出已启用且允许调用的文件系统操作
和命名自动化。每次调用验证输入/输出 Schema、复验权限，并对 ask 策略要求批准。
输入/输出限制为 16/64 KiB；不会自动重试，副作用不确定时明确报告。超时由原适配器
负责，目录会标明是否有超时约束。单次调用层不需要 API Key，也被下方动态循环复用。
详见[工具契约设计](docs/superpowers/specs/2026-09-09-execution-tool-contracts.md)和
[初步开源比较](docs/execution_framework_evaluation.md)。

## 动态执行（Phase 15.2-15.3）

15.4a 已接入显式选择的目标、RAG 记忆和研究项目上下文；15.4b 已接入文字/语音共享任务。
详见[上下文设计](docs/superpowers/specs/2026-09-13-execution-context-design.md)和下方用法。

```powershell
pip install -e ".[executor]"
nexus executor run "读取 README.md，总结项目当前的功能边界" --max-steps 12 --timeout-seconds 120
```

先配置 LLM 和授权工具。模型每次选择一个动作，观察真实工具结果后继续、提问或停止。
已注册的 allow 工具可以执行；ask 工具在执行前返回待审批动作，批准绑定当前任务、
具体动作及工具配置，不提供全局批准开关。工具数据可能发送到已配置的 LLM；运行时关闭 LangSmith tracing。
时间预算在步骤间检查并传给模型请求，工具仍使用自己的超时机制，不保证强制中断所有阻塞调用。

`reported_complete` 表示模型提供了成功工具结果的引用，不代表任务已独立验收通过。
其他状态区分审批/补充信息等待、预算耗尽、失败、重复和副作用不确定。CLI 任务保存在
`NEXUS_HOME/executor.sqlite3`，默认 `.nexus/executor.sqlite3`。用 `resume` 继续同一任务；
再次 `run` 会创建新任务。选定来源的 RAG 上下文及文字/语音共享入口已可用，通用 MCP 执行适配器仍属于后续阶段。

```powershell
nexus executor runs
nexus executor show RUN_ID
nexus executor resume RUN_ID --approval-token TOKEN_FROM_SHOW
nexus executor resume RUN_ID --answer "使用项目目录"
nexus executor pause RUN_ID
nexus executor resume RUN_ID
nexus executor cancel RUN_ID
```

审批前查看待执行工具及参数。工具配置变化会使令牌失效，需要重新查看并批准。
列表、详情、暂停/取消请求和人工核对不需要 API；恢复执行需要配置模型。
暂停和取消是执行边界上的协作式请求，不会强制杀死外部软件。取消不可撤回。
恢复保留累计步骤、重复动作记录及实际运行时间预算，等待用户的时间不计入预算；
预算耗尽后不会自动重置。

若进程在工具调用中退出，恢复进入 `needs_review`，不会自动重做。先检查真实目标状态，
再记录一种核对结果：

```powershell
nexus executor resolve RUN_ID --outcome completed --note "已人工确认目标结果"
# 或者，仅在确认操作没有发生时：
nexus executor resolve RUN_ID --outcome not-executed --note "已确认目标未被修改"
```

核对命令不执行工具，记录的是用户证据，不是假造的工具成功。核对后任务暂停或保持取消，
后续恢复仍需遵守工具审批。部分完成或仍然不确定的操作应继续等待核对。
这不承诺跨系统的 exactly-once 执行。快照含目标、回答和工具结果，未加密，不能发布到 GitHub；
任务库不会复制厂商 Key 和配置，但工具返回的敏感数据仍需妥善保护。
详见[持久执行设计](docs/superpowers/specs/2026-09-12-durable-execution.md)。

## 执行上下文（Phase 15.4a）

[文字/语音共享任务](docs/superpowers/specs/2026-09-14-shared-task-conversation-design.md)（15.4b）已实现，
目标是围绕同一个任务持续协作，但当前不支持语音打断或后台执行。

必须显式启用，不带新参数的原有命令行为不变。把示例 ID 替换为自己的目标和研究项目 ID：

```powershell
nexus executor run "结合我的目标，检查下一步研究任务" --with-context --context-goal GOAL_ID --context-research RESEARCH_ID
nexus executor run "安排一个专注学习步骤" --with-context --context-memory-scope private --allow-sensitive-context
```

选定目标/研究字段和相关记忆可能发送到已配置的 LLM。记忆默认仅检索 `shared`；
使用 `personal` 或 `private` 必须加 `--allow-sensitive-context` 明确同意，不会扩大工具权限。
配置的 RAG 可能向 Embedding 厂商发送任务查询；本功能不自动重建索引，也不额外调用 LLM 压缩上下文。

限制为三个不重复目标、五条相关记忆、一个研究项目、五个开放问题；每个文本字段最多 1,000 字符，
整体 UTF-8 JSON 最多 16 KiB。研究内容只包含目标、问题和数量摘要，不加载论文全文、笔记或实验输出。
`executor show RUN_ID` 可查看来源、检索策略/分数、截断标记和不含敏感原始异常的降级原因。

恢复复用原快照，不重新检索。引用来源被删除、过期、归档、修改或改变隐私范围时，
返回 `context_invalid` 并阻止继续，保留待审批状态；每次模型/工具调用前也会校验。
当前没有自动刷新或重启功能，已经可能产生副作用的任务不要直接从头重跑。
校验无法撤回已发送给厂商的数据，也不会自动擦除历史明文任务快照。
上下文引用只是背景信息，不能冒充工具执行成功证据。

## 文件验收检查（Phase 15.5a）

创建任务时通过 `executor run --acceptance` 提前声明验收条件。条件固定保存在任务中，
模型不能在结束时自行降低标准，恢复任务也不能替换条件。条件中的路径和期望文本会进入模型提示，
但不会因此获得新的文件权限。以下检查已有文档，请替换为已授权读取目录中的实际文件：

```powershell
$acceptance = @{checks=@(@{path='D:/Projects/example/README.md';kind='nonempty'})} | ConvertTo-Json -Depth 5 -Compress
nexus executor run "读取项目 README，总结当前限制" --acceptance $acceptance
nexus executor verify RUN_ID
nexus ask "查看进度" --task-mode --task-id RUN_ID
```

支持四类条件：`exists`（能够读取普通文件）、`nonempty`（非空）、
`contains`（另填 `value` 指定文本）、`json_fields`（另填 `fields`，如 `{"title":"string","count":"integer"}`）。
JSON 验证限顶层字段类型，不是任意 Schema 或内容质量判断。
任务模式的自然语言创建暂不接收验收条件，可先通过 executor 创建，再选中同一个任务继续协作。

模型报告完成后自动执行本地只读检查。任务生命周期仍是 `reported_complete`，
另用 `verification_report.status` 区分全部通过 `passed`、部分通过 `partial`、
检查失败 `failed`、无法验证 `unverifiable`，并记录时间和每项原因。
通过仅证明检查时指定条件成立，不证明文件由本任务创建，更不等于整个开放目标已完成。
没有验收条件的旧任务保持原行为；声明了条件却未全部通过时，run/resume/verify 返回非零退出码。

复查命令 `executor verify` 不调用 LLM，不重跑任务操作。限制为 1–20 项、16 KiB 条件、
每次最多读取 16,000 字节、协作式 5 秒检查预算（不能强行中断已经阻塞的读取）。
权限拒绝、缺失/不可读、截断或解码不确定时不会冒充验证成功。
报告不保存文件正文，语音只概括验证状态；条件和路径仍是本地明文。
保留最近报告与最多十份历史报告。检查中断后可再次 verify，文件后续变化也可能改变结论。

带验收条件的任务追问同样只在文字中展示，包括尚未调用工具时的首次追问，避免模型复述私人条件。

## 文字/语音共享任务（Phase 15.4b）

显式开启任务模式后，文字和语音围绕同一个持久任务协作；普通对话行为不变。

```powershell
nexus ask "开始任务：读取项目 README 并总结当前限制" --task-mode
nexus ask "查看进度" --task-mode
nexus voice chat --task-mode
nexus ask "回答：使用项目目录" --task-mode
nexus ask "继续任务" --task-mode
```

两个入口默认使用本地 `default` 会话，重启后仍记得选中的任务。需要区分工作流时，
在两个入口都加 `--task-session research`。会话名只是本地标签，不是用户认证或隐私隔离。
也可以选中已有任务，包括带 15.4a 上下文的任务：

```powershell
nexus ask "查看进度" --task-mode --task-id RUN_ID
nexus ask "任务列表" --task-mode
nexus ask "选择任务 2 @REVISION" --task-mode
nexus ask "暂停任务" --task-mode
nexus ask "取消任务" --task-mode
```

未选中任务时最多展示五个候选，不会擅自挑最新一个。编号指向已展示列表的 ID 快照；
把 REVISION 替换为列表返回的 selection_revision。新 CLI 进程需要这个列表版本号或完整任务 ID；
连续语音会话可直接使用自己展示过的编号。另一入口刷新列表或改选后，旧版本选择会被拒绝。
已经开始处理的一次请求不会因另一入口改选而换目标。
若创建时发生选择冲突，可能留下一个未执行的 `created` 任务，可在列表中查看；不会自动执行或重试。

生命周期命令使用确定性的中英文短语识别，不会把任意闲聊自动变成执行。
只有选中任务正在等待补充信息时，非控制语句才会作为回答。新任务默认不附加个人上下文，
已有上下文任务继续沿用原来的授权和来源校验。

查询、选择、暂停和取消不初始化 LLM 或 Embedding；执行仍需要配置模型，并遵守原有预算和工具权限。
空闲任务取消后会在任务锁保护下立即确认状态；执行中的调用仍是协作式取消，结果不确定的动作仍需人工核对。
任务模式拒绝 `--approve`，“好的”或“yes”都不是工具审批。
需要批准时先用 `executor show RUN_ID` 检查具体动作，再通过
`executor resume RUN_ID --approval-token TOKEN` 提交对应令牌。
任务模式语音可在待审批时继续接收安全的查询/控制；普通语音仍在审批时退出。
播报不朗读审批令牌和原始工具结果，并区分等待、失败以及“模型报告完成”。
如果追问发生在读取工具结果或附加上下文之后，问题保留在文字视图中，语音只提示查看并回答，避免复述潜在私人信息。

当前是前台轮流会话：工具或模型阻塞时不会同时监听“停下”，也没有后台执行服务。
可从另一个文字进程发起协作式取消。自动化测试使用模拟音频和脚本模型，不等于已完成真实麦克风和识别准确率验收。

## 电脑本地任务

Desktop Task Agent 基础版已将文字和语音接入授权目录文件名搜索、已注册应用和网址启动。
将示例目录替换为你自己的现有目录，再注册项目附带的 ChatGPT 网页定义：

```powershell
nexus config tool set filesystem --root "D:/Pictures"
nexus automation set chatgpt --definition (Get-Content -Raw examples/desktop-chatgpt.json)
nexus ask "帮我找到我本地的护照照片"
nexus ask "打开chatgpt"
nexus ask "打开chatgpt" --approve
nexus ask "打开文件 D:/Pictures/passport.jpg" --approve
nexus ask "Hi Nexus，帮我打开Chatgpt，我们开始今天的任务" --approve
```

搜索包含图片文件，返回候选编号、路径、大小、修改时间和是否截断。“护照照片”也会匹配
文件名中的 `passport`。每个目录扫描最多 10,000 个条目、50 个匹配、5 秒，最多扫描 10 个
授权根目录；跳过隐藏项、符号链接和目录联接。本版尚无 OCR、缩略图界面或图片内容识别，
所以无法从随机文件名判断哪张是护照照片。

同一次 `voice chat` 中可以接着说“打开第二张”，引用最近一次搜索。打开文件需要一次性批准
和文件系统读取权限，仅支持常见图片、PDF、TXT、Markdown。语音会话在批准预览处停止；
可用预览中的明确路径执行 `nexus ask "打开文件 ..." --approve`。候选编号不会跨 CLI 调用保留。

Windows 桌面应用通过 `nexus automation set <别名> --definition` 注册，例如
`{"type":"application","executable":"C:/Apps/Example/app.exe","policy":"ask"}`，
程序必须是现有的绝对 `.exe` 路径，不接受对话传入的启动参数。应用和网址沿用 `deny/ask/allow`
策略；你明确设为 `allow` 的可信别名可以在语音会话中直接启动。`Hi Nexus` 只是可选文字前缀，
并非唤醒词。

启动结果表示操作系统已接收请求，尚未检查窗口、登录状态或点击软件界面。本地文件与应用
启动目前面向 Windows，网址复用已有浏览器适配器。“开始今天的任务”会打开注册别名并列出
今日任务，不会自动执行这些任务。本次没有引入 OpenClaw 代码或运行依赖。

## 本地语音助手

纯文本 Nexus 无需语音依赖或 API key 仍可正常使用。只有需要显式本地录音、转写或语音输出时，才安装可选语音依赖：

```bash
pip install -e ".[voice]"
nexus config voice set --enable --model small --language auto
nexus voice ask --record-seconds 5
nexus voice chat --max-turns 20 --idle-seconds 30
nexus voice briefing --live-tools
```

`nexus voice ask` 按请求的有限时长录音，在本地转写 WAV，将文字交给与 `nexus ask` 相同的对话与批准流程，并在操作系统语音可用时播报结果。`nexus voice briefing` 复用现有文本简报，也可使用显式请求的实时工具。可用 `nexus voice status`、`nexus voice record`、`nexus voice transcribe` 和 `nexus voice speak` 进行诊断或单项操作。

`nexus voice chat` 启动 Voice Assistant 2.0 连续轮流会话：WebRTC VAD 等待说话，检测到约 900 毫秒停顿后结束本轮录音。Nexus 处理并播报后自动再次监听。说“结束对话”或 `end conversation`、按 Ctrl+C，或等待静默超时即可退出。普通会话遇到待审批操作时退出并输出预览，任务模式则可继续查询/控制但不能语音批准；审批不会跨轮继承。`--no-play` 只输出文字。会话事件以实时刷新的 JSON 行输出。默认最多录音尝试 20 轮（上限 100），每轮等待说话 30 秒（上限 120）；空转写消耗一次尝试后继续监听。

升级时重新运行 `pip install -e ".[voice]"` 安装 `webrtcvad-wheels`。音频始终保留在本地，临时录音会被删除；Whisper 首次运行可能下载模型。添加 `--llm` 可使用已配置的文本 LLM 解析意图，此时转写文字可能发送给该厂商。会话复用现有命令路由，没有新增聊天历史推理或代词消解。处理和播报时暂停监听；唤醒词、语音打断、后台监听和 Dashboard 麦克风仍待实现。

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
nexus suggestion refresh --live-tools
nexus suggestion list
nexus tool audit --limit 20
```

建议刷新始终使用已配置的 RAG 管线；`--live-tools` 会额外读取已配置的日历。任一依赖失败时都会独立降级，同时保留本地目标、任务、习惯和项目建议。可选 LLM 只能润色措辞。

## Research Companion 研究伙伴

创建证据导向的研究工作区，并记录来源、笔记和实验：

```bash
nexus research create "RAG 评估" --objective "比较稠密与混合检索" --question "什么方法能提升召回率？"
nexus research source-add <research-id> --type paper --title "混合检索研究" --locator "https://doi.org/..." --note "报告了召回率提升"
nexus research note-add <research-id> "该基准结果仍需复现" --source-id <source-id> --tag evaluation
nexus research experiment-add <research-id> "稠密与混合检索对比" --hypothesis "混合检索提升召回率" --method "比较二十条查询" --result "混合检索多找回两条记忆" --status completed
```

本地综合与后续问答会使用符合隐私策略的 RAG 记忆，不需要 API Key：

```bash
nexus research synthesize <research-id>
nexus research ask <research-id> "混合检索是否提升了召回率？"
nexus research list
nexus ask "查看研究项目"
```

安装可选 PDF 依赖，然后从用户明确指定的本地文件、HTTPS 页面或代码仓库建立研究语料库：

```bash
python -m pip install -e ".[research]"
nexus research document-add <research-id> ./paper.pdf
nexus research document-add <research-id> ./notes.md
nexus research web-add <research-id> https://example.org/article
nexus research repo-index <research-id> ./my-repository
nexus research document-list <research-id>
nexus research document-search <research-id> "混合检索 召回率"
nexus research run <research-id> "混合检索是否提升召回率？" --max-cycles 3
```

PDF 引用保留页码，文本、网页和仓库引用保留行号。`document-show`、`document-remove` 和 `document-reindex` 管理语料库。相同内容不会重复索引，重建失败会保留上一个有效索引，每条文档引用都会根据 Chunk 内容哈希验证。

实验必须显式批准，并使用参数数组、程序白名单、允许的工作目录、超时、最小环境、`shell=False` 和输出上限：

```bash
nexus research experiment-run <research-id> --cwd ./experiment --allowed-root ./experiment --allow-executable python --approve --command python evaluate.py
```

它是受限进程运行器，不是内核或容器沙箱；研究循环不会隐式联网或执行命令。

需要检索学术元数据时，再显式启用工具：

```bash
nexus config tool set literature --mailto "researcher@example.com"
nexus tool literature --query "retrieval augmented generation evaluation" --limit 5
nexus research investigate <research-id> --query "hybrid retrieval evaluation" --live-tools
```

`literature` 只调用 Crossref 固定的只读 `/works` 接口并导入有界书目元数据，不会下载或阅读论文全文。`--llm --model-tier complex` 可以润色综合和回答，但证据引用及不确定性完全由确定性逻辑控制。Literature、RAG 与 LLM 可以独立降级。

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

Dashboard 现在包含九个视图。Today 展示日程、任务、提醒和最近的简报/复盘；Habits 可以打卡，Projects 可以进行带修正保护的进度更新，Research 展示有界研究问题、来源/实验数量和最新综合，Suggestions 会在接受/忽略前展示 Calendar/RAG 来源类型和降级状态，Today 还提供重新规划预览/应用。Goals、可检索记忆、受限活动摘要和脱敏配置继续采用隐私过滤。

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

本地记忆、目标、规划、任务更新、打卡、确定性简报/复盘、主动调度、通知收件箱、Dashboard、本地稀疏检索、FastEmbed、确定性报告、本地网页/命令自动化和初始本地语音路径都不需要 API key。

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
- Research Companion 不执行 OCR、JavaScript 渲染浏览、登录态爬取、任意 Shell、容器隔离或无边界后台研究。网页摄取必须提供明确 HTTPS URL；受限实验运行器不等于操作系统沙箱。
- 语音录音必须显式启动且有时长上限。连续轮流监听仅在 `voice chat` 运行期间启用；唤醒词、说话人识别、语音打断和 Dashboard 麦克风访问尚未实现。
- Nexus 当前不提供开放式自主运行、远程 Dashboard、浏览器任意写操作、LLM 任意生成命令、视觉上下文、智能家居控制或机器人能力。

## CLI 命令地图

```bash
nexus memory add|list|show|search|retrieve|update|relate|archive|restore|forget|purge|compress|maintain|reindex|index-status
nexus goal add|list|check-in
nexus habit add|list|check-in|archive
nexus project add|list|milestone-add|milestone-update|progress|archive
nexus research create|list|show|question-add|source-add|note-add|experiment-add|investigate|synthesize|ask|archive|document-add|document-list|document-show|document-remove|document-reindex|document-search|web-add|repo-index|experiment-run|run
nexus suggestion list|refresh|accept|dismiss
nexus replan preview|apply
nexus ask TEXT [--approve] [--llm] [--show-intent]
nexus plan day
nexus task list|update
nexus review
nexus review day
nexus briefing
nexus tool weather|calendar|todo|github|notion|literature|email|files|audit
nexus mcp servers|tools|call|audit
nexus mcp-server stdio [--approve-tool NAME]
nexus agent runs|show
nexus voice status|record|transcribe|speak|ask|chat|briefing

nexus config llm set|show
nexus config embedding set|show
nexus config tool set|disable|show
nexus config mcp add|disable|remove|policy|planning-tool|show
nexus config profile show|set
nexus config runtime show|set
nexus config voice set|show|disable

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

Phase 1-12 与 Research Companion 2.0 已完成。Phase 13 已包含 Voice Assistant MVP 和 Voice Assistant 2.0 前台连续轮流会话。唤醒词、语音打断、视觉上下文及具身接口仍待实现。

持续监听与唤醒词、视觉上下文、家庭成员配置、智能家居适配器和机器人能力仍是未来工作，并且必须复用同一套权限和审计边界。
