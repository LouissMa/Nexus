# 🌟 LifeAgent

> **Proactive Personal AI OS with Long-Term Memory.** > An AI that doesn't just chat, but remembers your life, tracks your progress, and proactively helps you achieve your goals.

[English](./README.md) | [中文](./README_zh.md)

---

## 💡 Vision

Current AI tools are entirely passive: **You ask → AI answers.** LifeAgent breaks this paradigm. It acts as your personal digital twin and life manager. It remembers your context, understands your long-term objectives, and initiates conversations to keep you on track.

## ✨ Core Features

* **🧠 Long-Term Memory Engine**: Remembers your habits, career goals, relationships, and past conversations.
* **🔔 Proactive Intelligence**: Analyzes your progress and initiates reminders, encouragement, or course corrections without you prompting it.
* **🎯 Personal Goal Tracking**: Keeps your KPIs (health, learning, productivity) in check over months and years.

## 🚀 MVP (Minimum Viable Product)

Our initial release focuses strictly on establishing the foundational loop:
1.  **Memory System**: Store and retrieve user context.
2.  **Goal Tracking**: Define and monitor specific user objectives.
3.  **Proactive Reminders**: Time-based and context-aware push notifications via AI.

## 🔮 Future Vision

As the memory graph grows, LifeAgent will evolve into a complete Life Management OS:
* Automated Calendar & Task Management
* Smart Email Triage & Auto-replies
* A true Digital Persona with an emotional moat

## 🛠️ Tech Stack (Planned)

| Component | Technology |
| :--- | :--- |
| **Frontend** | React / Flutter |
| **Backend** | Python / Node.js |
| **AI / LLM** | OpenAI / Anthropic APIs |
| **Memory** | Vector Database (e.g., Pinecone, Supabase) |

## 🗺️ Roadmap

- [ ] **Phase 1**: Core Memory System & RAG implementation.
- [ ] **Phase 2**: Proactive Trigger Engine (Cron jobs + LLM logic).
- [ ] **Phase 3**: Evolution into a full Personal AI Agent.

## CLI MVP

The repo now includes a local Phase 1 CLI MVP that proves the first product loop:

- Store long-term memories
- Track user goals
- Run a proactive review that flags stale goals or missing life updates

### Quick Start

```bash
python -m pip install -e .
nexus memory add "User wants to exercise every morning" --tags health routine
nexus goal add "Morning workout" --description "20 minutes daily" --cadence-days 2
nexus review
```

Data is stored locally in `.nexus/state.json`. Set `NEXUS_HOME` to move storage elsewhere.
