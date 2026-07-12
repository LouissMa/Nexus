# Nexus / LifeAgent：你的个人 AI 管家

> **一个具备长期记忆和主动性的个人 AI 操作系统。**

Nexus 不是普通聊天机器人，而是一个像 J.A.R.V.I.S. 一样的个人生活助手。它会记住你的目标、理解你的日程和生活上下文，并在合适的时候提醒你、帮助你、陪你完成任务。

[English](./README.md) | [中文](./README_zh.md)

---

## 项目定位

大多数 AI 助手都是被动的：用户提问，它才回答。

Nexus 不同。

Nexus 是一个主动型个人 AI 管家。它会记住你的长期目标，理解你的生活上下文，追踪你的进度，并每天主动帮助你行动。

项目方向从 **Proactive Personal AI** 升级为：

> **Personal AI Operating System**

## 当前版本功能

- **添加记忆**：记录身份、偏好、学习计划、考试、项目进展、重要的人和事。
- **搜索记忆**：按关键词搜索本地长期记忆。
- **添加目标**：创建长期或短期目标，并设置目标检查周期。
- **目标打卡**：为某个目标记录进展，例如“今天完成 IELTS 听力训练”。
- **主动复盘**：发现长时间没有推进的目标，并生成提醒。
- **早晨简报**：根据记忆和目标生成当天的生活简报，包括日期、天气文本、重要目标、提醒和建议。
- **LLM 智能简报**：可选接入 OpenAI-compatible LLM，用记忆、目标、提醒和天气文本生成更自然的简报。
- **Prompt 查看**：使用 `--show-prompt` 查看发送给 LLM 的系统提示词和用户提示词。
- **本地存储**：MVP 数据默认保存到 `.nexus/state.json`。

## 快速开始

```bash
python -m pip install -e .

nexus memory add "Louis 正在准备 IELTS，并计划申请海外 CS/AI 硕士。" --tags 身份 学习
nexus memory add "Louis 正在开发 Nexus，希望把它做成个人 AI 管家。" --tags 项目 Nexus
nexus goal add "IELTS 听力训练" --description "完成一次专注听力训练" --cadence-days 1
nexus goal add "开发 Nexus" --description "完成早晨简报模块" --cadence-days 2
nexus briefing --name Louis --weather "天气晴，最高 25 C"
```

## LLM 智能简报

Nexus 不配置 API key 也能运行。传入 `--llm` 但没有配置 key 时，系统会自动退回本地模板，并在 JSON 的 `llm.error` 里说明原因。

### 我需要填写 API key 吗？

只有在你想使用 LLM 生成智能简报时才需要。

- 不使用 API key：记忆、目标、打卡、主动复盘、模板早晨简报都可以正常运行。
- 需要 API key：当你运行 `nexus briefing --llm` 时，系统才会尝试调用 LLM。
- 不要把 API key 写进代码，也不要提交到 GitHub。请放在 `OPENAI_API_KEY` 或 `NEXUS_LLM_API_KEY` 这样的环境变量里。
- 如果没有配置 key，Nexus 仍会返回可用的模板简报，并在 `llm.error` 里说明原因。

启用 LLM：

```bash
$env:OPENAI_API_KEY="your-api-key"
nexus briefing --llm --name Louis --weather "天气晴，最高 25 C"
```

可选环境变量：

```bash
$env:NEXUS_LLM_API_KEY="your-api-key"        # 优先级高于 OPENAI_API_KEY
$env:NEXUS_LLM_MODEL="gpt-4o-mini"           # 默认模型
$env:NEXUS_LLM_BASE_URL="https://api.openai.com/v1"
$env:NEXUS_LLM_TIMEOUT_SECONDS="30"
```

查看 LLM prompt：

```bash
nexus briefing --llm --show-prompt --name Louis
```

没有配置 API key 时的 fallback 示例：

```json
{
  "llm": {
    "requested": true,
    "used": false,
    "error": "LLM client is not configured."
  }
}
```

## CLI 命令

```bash
nexus memory add "..." --tags 学习 项目
nexus memory list
nexus memory search IELTS

nexus goal add "开发 Nexus" --description "完成 MVP 功能" --cadence-days 2
nexus goal list
nexus goal check-in <goal_id> "完成了第一版实现。"

nexus review
nexus briefing --name Louis --weather "天气晴，最高 25 C"
nexus briefing --llm --show-prompt --name Louis
```

## 后续路线

- **Phase 1：LifeAgent CLI MVP**：记忆、目标、打卡、早晨简报。
- **Phase 2：LLM 智能简报**：prompt 组装、OpenAI-compatible LLM client、安全降级。当前升级已完成。
- **Phase 3：RAG 长期记忆**：用向量检索增强记忆召回。
- **Phase 4：每日复盘与教练模式**：晚间复盘、严格模式、温柔模式、学术模式、创业模式。
- **Phase 5：生活仪表盘**：今日任务、长期目标、记忆时间线、习惯追踪、项目进度、AI 建议。
- **Phase 6：工具与 Agent**：MCP 工具调用、浏览器自动化、多 Agent planning/reflection。

## 数据存储

数据默认保存在 `.nexus/state.json`。如果你想换位置，可以设置 `NEXUS_HOME` 环境变量。

