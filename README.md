# Nexus / LifeAgent

> **A proactive personal AI operating system for daily life.**

Nexus is not a normal chatbot. It is a J.A.R.V.I.S.-like personal AI assistant that remembers your goals, understands your life context, and helps you take action every day.

[English](./README.md) | [Chinese](./README_zh.md)

---

## Product Direction

Most AI assistants are passive. They wait for users to ask questions.

Nexus is different.

Nexus is a proactive personal AI assistant that manages daily life, remembers long-term goals, tracks progress, and generates useful guidance at the right moment.

The long-term vision is to build a **Personal AI Operating System** for everyday life.

## MVP Focus

The first version stays intentionally small. It proves one core loop:

1. Remember who the user is.
2. Know what the user wants to do.
3. Track progress through check-ins.
4. Generate a daily proactive briefing.

## Current Version Features

- **Add Memory**: Store long-term context such as identity, preferences, plans, exams, projects, and important life facts.
- **Add Goal**: Create goals with descriptions and check-in cadence.
- **Goal Check-In**: Record progress notes for a goal.
- **Proactive Review**: Detect goals that have been quiet for too long.
- **Morning Briefing**: Generate a daily life briefing with date, weather text, important goals, reminders, and one suggested next action.
- **Local JSON Storage**: Keep all MVP data in `.nexus/state.json` by default.

## Example Morning Briefing

```text
Good morning, Louis.

Today is June 4. Weather: sunny, high 25 C.

You have 3 important things today:

1. Operating systems review
2. IELTS listening practice
3. Continue developing Nexus

I suggest you start with "Continue developing Nexus" and finish one 30-minute task.

You do not need to finish everything today. Move the most important step forward first.
```

## Quick Start

```bash
python -m pip install -e .

nexus memory add "Louis is preparing for IELTS and wants to apply for an overseas CS/AI master's program." --tags identity study
nexus goal add "IELTS listening practice" --description "Complete one focused listening session" --cadence-days 1
nexus goal add "Develop Nexus" --description "Build the morning briefing module" --cadence-days 2
nexus briefing --name Louis --weather "weather is sunny, high 25 C"
```

## CLI Commands

```bash
nexus memory add "..." --tags study project
nexus memory list
nexus memory search IELTS

nexus goal add "Develop Nexus" --description "Ship MVP features" --cadence-days 2
nexus goal list
nexus goal check-in <goal_id> "Finished the first implementation."

nexus review
nexus briefing --name Louis --weather "weather is sunny, high 25 C"
```

## Roadmap

- **Phase 1: LifeAgent CLI MVP**: memory, goals, check-ins, morning briefing.
- **Phase 2: Daily Review and Modes**: evening review, strict/gentle/academic/startup coaching modes.
- **Phase 3: Life Dashboard**: web dashboard for goals, memory timeline, habits, and AI suggestions.
- **Phase 4: Integrations**: calendar, weather API, email, todo apps, Notion, GitHub, and health data.
- **Phase 5: Personal AI OS**: proactive planning, permissioned task execution, and deeper long-term personalization.

## Storage

Data is stored locally in `.nexus/state.json`. Set `NEXUS_HOME` to move storage elsewhere.
