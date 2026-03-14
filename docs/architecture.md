# 🏗️ System Architecture (MVP Phase)

NEXUS operates on a decoupled architecture, separating the core AI logic from the frontend interfaces.

## High-Level Data Flow

```text
[User] 
  │
  ▼ (Text Input via CLI / Telegram Bot)
[Frontend Interface]
  │
  ▼ (API Request)
[Backend Server (Python/Node)] ◄────────── [Proactive Engine / Cron Job]
  │                                                │
  ├─► [Memory Engine]                              │ (Timer triggers AI
  │     │                                          │  to check on user)
  │     ▼                                          │
  │   [Vector DB (Context/History)]                │
  │   [SQL DB (Goals/Habits)]                      │
  │                                                │
  └─► [LLM Controller] ◄───────────────────────────┘
        │
        ▼
      [LLM API (OpenAI/Anthropic)]

[用户 User] 
  │
  ▼ (通过命令行或 Bot 输入文本)
[前端交互层 Frontend]
  │
  ▼ (API 请求)
[后端服务器 Backend] ◄───────────────────── [主动引擎 Proactive Engine]
  │                                                │
  ├─► [记忆引擎 Memory Engine]                     │ (定时器触发 AI
  │     │                                          │  主动检查用户状态)
  │     ▼                                          │
  │   [向量数据库 (存对话/上下文)]                   │
  │   [关系型数据库 (存目标/习惯)]                   │
  │                                                │
  └─► [模型控制器 LLM Controller] ◄────────────────┘
        │
        ▼
      [外部大模型 API (如 OpenAI)]