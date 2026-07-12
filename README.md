# Nexus / LifeAgent

> **A proactive personal AI operating system for daily life.**

Nexus is not a normal chatbot. It is a J.A.R.V.I.S.-like personal AI assistant that remembers your goals, understands your life context, and helps you take action every day.

[English](./README.md) | [Chinese](./README_zh.md)！

---

## Product Direction

Most AI assistants are passive. They wait for users to ask questions.

Nexus is different.

Nexus is a proactive personal AI assistant that manages daily life, remembers long-term goals, tracks progress, and generates useful guidance at the right moment.

The long-term vision is to build a **Personal AI Operating System** for everyday life.

## Current Version Features

- **Add Memory**: Store long-term context such as identity, preferences, plans, exams, projects, and important life facts.
- **Search Memory**: Search local memories by keyword.
- **Add Goal**: Create goals with descriptions and check-in cadence.
- **Goal Check-In**: Record progress notes for a goal.
- **Proactive Review**: Detect goals that have been quiet for too long.
- **Morning Briefing**: Generate a daily life briefing with date, weather text, important goals, reminders, and one suggested next action.
- **LLM Briefing Mode**: Optionally use an OpenAI-compatible LLM to write a more natural briefing from memories, goals, reminders, and weather text.
- **Prompt Inspection**: Use `--show-prompt` to inspect the exact system/user prompt sent to the LLM.
- **Local JSON Storage**: Keep all MVP data in `.nexus/state.json` by default.

## Quick Start

```bash
python -m pip install -e .

nexus memory add "Louis is preparing for IELTS and wants to apply for an overseas CS/AI master's program." --tags identity study
nexus goal add "IELTS listening practice" --description "Complete one focused listening session" --cadence-days 1
nexus goal add "Develop Nexus" --description "Build the morning briefing module" --cadence-days 2
nexus briefing --name Louis --weather "weather is sunny, high 25 C"
```

## LLM Briefing

Nexus works without an API key. If you pass `--llm` without configuring a key, it safely falls back to the local template and reports the LLM error in JSON.

### Do I Need an API Key?

Only if you want LLM-generated briefings.

- No API key is required for local memory, goals, check-ins, proactive review, or template morning briefing.
- An API key is required when you run `nexus briefing --llm`.
- Never commit API keys to GitHub. Store them in environment variables such as `OPENAI_API_KEY` or `NEXUS_LLM_API_KEY`.
- If no key is configured, Nexus still returns a valid template briefing and includes the reason in `llm.error`.

To enable LLM generation:

```bash
$env:OPENAI_API_KEY="your-api-key"
nexus briefing --llm --name Louis --weather "weather is sunny, high 25 C"
```

Optional environment variables:

```bash
$env:NEXUS_LLM_API_KEY="your-api-key"        # takes priority over OPENAI_API_KEY
$env:NEXUS_LLM_MODEL="gpt-4o-mini"           # default model
$env:NEXUS_LLM_BASE_URL="https://api.openai.com/v1"
$env:NEXUS_LLM_TIMEOUT_SECONDS="30"
```

Inspect the prompt without guessing what context is used:

```bash
nexus briefing --llm --show-prompt --name Louis
```

Example fallback response when no key is configured:

```json
{
  "llm": {
    "requested": true,
    "used": false,
    "error": "LLM client is not configured."
  }
}
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
nexus briefing --llm --show-prompt --name Louis
```

## Roadmap

- **Phase 1: LifeAgent CLI MVP**: memory, goals, check-ins, morning briefing.
- **Phase 2: LLM Briefing**: prompt assembly, OpenAI-compatible LLM client, safe fallback. Completed in the current upgrade.
- **Phase 3: RAG Memory**: vector search over long-term memories.
- **Phase 4: Daily Review and Modes**: evening review, strict/gentle/academic/startup coaching modes.
- **Phase 5: Life Dashboard**: web dashboard for goals, memory timeline, habits, and AI suggestions.
- **Phase 6: Integrations and Agents**: MCP tools, browser automation, multi-agent planning/reflection.

## Storage

Data is stored locally in `.nexus/state.json`. Set `NEXUS_HOME` to move storage elsewhere.

