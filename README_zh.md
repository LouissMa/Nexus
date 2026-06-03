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

第一版目标：

> 先做一个每天早上会主动给你生活简报、目标提醒和学习建议的 AI 管家。

## MVP 核心闭环

第一版不要做太大，只先跑通 4 个功能：

1. 添加记忆
2. 添加目标
3. 目标打卡
4. 每日主动简报

也就是：

```text
记住我是谁
知道我要做什么
提醒我该做什么
每天早上总结给我
```

## 当前版本功能

- **添加记忆**：记录身份、偏好、学习计划、考试、项目进展、重要的人和事。
- **添加目标**：创建长期或短期目标，并设置目标检查周期。
- **目标打卡**：为某个目标记录进展，例如“今天完成 IELTS 听力训练”。
- **主动复盘**：发现长时间没有推进的目标，并生成提醒。
- **早晨简报**：根据记忆和目标生成当天的生活简报，包括日期、天气文本、重要目标、提醒和建议。
- **本地存储**：MVP 数据默认保存到 `.nexus/state.json`。

## 早晨简报示例

```text
早上好，Louis。

今天是 6月4日，天气晴，最高 25 C。

你今天有 3 件重要的事：

1. 操作系统复盘
2. IELTS 听力训练
3. 开发 Nexus 项目

我建议你今天先推进「开发 Nexus 项目」，先做一个 30 分钟的小任务。

今天不用做完所有事，先把最重要的一步往前推。
```

## 快速开始

```bash
python -m pip install -e .

nexus memory add "Louis 正在准备 IELTS，并计划申请海外 CS/AI 硕士。" --tags 身份 学习
nexus memory add "Louis 正在开发 Nexus，希望把它做成个人 AI 管家。" --tags 项目 Nexus
nexus goal add "IELTS 听力训练" --description "完成一次专注听力训练" --cadence-days 1
nexus goal add "开发 Nexus" --description "完成早晨简报模块" --cadence-days 2
nexus briefing --name Louis --weather "天气晴，最高 25 C"
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
```

## 后续路线

- **Phase 1：LifeAgent CLI MVP**：记忆、目标、打卡、早晨简报。
- **Phase 2：每日复盘与教练模式**：晚间复盘、严格模式、温柔模式、学术模式、创业模式。
- **Phase 3：生活仪表盘**：今日任务、长期目标、记忆时间线、习惯追踪、项目进度、AI 建议。
- **Phase 4：外部集成**：日历、天气、邮件、待办事项、Notion、GitHub、健康数据。
- **Phase 5：个人 AI 操作系统**：主动规划、授权执行任务、更深层的长期个性化。

## 数据存储

数据默认保存在 `.nexus/state.json`。如果你想换位置，可以设置 `NEXUS_HOME` 环境变量。
