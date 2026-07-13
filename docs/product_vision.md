# Product Vision: Nexus / LifeAgent

## One-Sentence Description

**Nexus is a proactive, local-first personal AI assistant that remembers goals, builds plans, and helps users take action through permissioned tools.**

中文：

**Nexus 是一个具备长期记忆和主动性的个人 AI 管家，它会记住你的目标、理解你的日程，并每天主动帮助你规划生活。**

## Why Nexus Exists

Most AI assistants are passive. They wait for users to ask questions.

Nexus is designed around a different interaction model:

```text
AI remembers -> AI understands context -> AI notices timing -> AI helps the user act
```

The product should feel less like a search box and more like a personal life companion that knows what matters to the user.

## Core Product Feeling

The most important first experience is the morning briefing:

```text
早上好，Louis。

今天是 6月4日，天气晴，最高 25 C。

你今天有 3 件重要的事：

1. 上午 10:00 操作系统复盘
2. 下午 2:00 完成 IELTS 听力训练
3. 晚上继续开发 Nexus 项目

你昨天说今天想推进 AI 项目，所以我建议你今晚先完成目标提醒模块。

另外，你最近连续两天睡得比较晚，今天晚上建议 12 点前休息。
```

That is the emotional and product target: proactive, personal, contextual, and action-oriented.

## Product Principles

1. **Proactive before conversational**: Nexus should not only answer. It should remind, summarize, and suggest next actions.
2. **Memory before intelligence**: The assistant becomes useful because it remembers the user's goals, context, preferences, and progress.
3. **Small actions over big plans**: The assistant should turn goals into small, doable next steps.
4. **Trust through restraint**: The MVP should avoid pretending to know data it has not integrated yet. Weather, calendar, email, and health data should be explicit inputs until real integrations exist.
5. **Companion plus coach**: Nexus should support the user emotionally while still moving work forward.

## MVP Definition

The first version only needs four capabilities:

1. Add memory.
2. Add goal.
3. Check in on a goal.
4. Generate a daily proactive briefing.

This creates the first product loop:

```text
remember me -> know my goals -> track progress -> brief me every morning
```

## Long-Term Vision

Nexus can grow into a Personal AI Operating System:

- Morning briefing
- Long-term memory
- Goal tracker
- Real-time conversation
- Command system
- Daily review
- Personal coach modes
- Life dashboard
- Calendar, weather, email, todo, Notion, GitHub, and health integrations

## Long-Term Interface Direction

Nexus should remain one assistant core rather than a collection of disconnected apps. The same memory, planning, reflection, permission, and tool layers can later support:

- Voice input and speech output.
- Vision-based context from user-approved cameras.
- Smart-home devices and household context.
- Robotics adapters for navigation and physical tasks.
- Research workflows that combine web search, documents, code, experiments, and durable project memory.

These are research and integration directions. The project should describe them as future interfaces around the Nexus core, not as capabilities that already exist and not as a claim that Nexus is AGI.

## Scope Boundary

Nexus should earn trust incrementally. Every external action must use explicit permissions, observable tool calls, audit logs, and safe fallback behavior. Digital assistance comes first; multimodal sensing, home automation, and robotics are later extensions after memory, tools, planning, and orchestration are dependable.
