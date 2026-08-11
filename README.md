# Nexus / LifeAgent

> **A proactive, local-first personal AI assistant with long-term memory, planning, reflection, and permissioned action.**

Nexus remembers goals and life context, creates daily plans, runs scheduled briefings and reviews, coordinates bounded specialist agents, and connects only to tools you explicitly approve.

[English](./README.md) | [Chinese](./README_zh.md)

---

## Product Direction

Most assistants wait for a prompt. Nexus is being built as a dependable personal AI core that can remember, plan, remind, review, and perform named actions at the right time.

The long-term direction is a Personal AI Operating System shared by CLI, web, voice, and future embodied interfaces. The current release is not AGI: it is a local, permission-bounded assistant with explicit limits.

## Current Features

- Long-term memory with search, semantic RAG, Qdrant persistence, re-indexing, lifecycle controls, privacy, expiry, compression, and explainable re-ranking.
- Goals, check-ins, stale-goal detection, persistent daily tasks, blockers, unresolved items, evening reflection, and four Coach modes.
- Habit tracking with daily/weekday cadence, idempotent check-ins, streaks, completion rates, and archival.
- Project tracking with linked goals/tasks, milestones, derived or explicit progress, correction history, and archival.
- Explainable offline suggestions from quiet goals, blocked/pending tasks, habit risk, and milestone deadlines, with expiring snapshots and approval-gated actions.
- Calendar-aware replan previews and stale-safe apply, with read-only live iCalendar constraints, priority allocation, shortening, and explicit unscheduled reasons.
- Unified `nexus ask` entry point with common Chinese/English local intents, approval previews for mutations, low-risk habit check-ins, and optional strict-JSON LLM intent selection.
- Optional OpenAI-compatible LLM generation with local provider/model tiers and masked configuration.
- Read-only weather, iCalendar, Todoist, GitHub, Notion, IMAP-header, and bounded filesystem integrations.
- Permissioned MCP client over stdio or Streamable HTTP with schema discovery, deny/ask/allow policies, bounded retries, and secret-safe audits.
- Bounded Memory, Tool, Planner, Reflection, and Coach Agent coordination with budgets, fallback, and privacy-safe traces.
- Proactive morning briefing, evening review, and stale-goal reminder jobs in the user's IANA time zone.
- Durable inbox notifications, optional console/webhook delivery, and normal or overnight quiet hours.
- Responsive loopback Dashboard with Today, Goals, Habits, Projects, Suggestions, Memory, Activity, and masked Settings; six exact CSRF-protected actions cover atomic habit increments, progress, suggestion decisions, and live-calendar replan preview/apply.
- Permissioned Nexus stdio MCP Server with seven bounded read tools, five approval-gated mutation tools, per-tool deny/ask/allow policy overrides, and content-free secret-safe audit summaries.
- Named browser, command, GitHub-inspection, and Markdown status-report automations under explicit policies.

## Quick Start

Install the core package and create a local profile:

```bash
python -m pip install -e .
nexus config profile set --name Alex --timezone Asia/Shanghai
nexus config profile show
```

Add context and create today's plan:

```bash
nexus memory add "Alex is preparing for IELTS." --tags study exam
nexus goal add "IELTS listening" --description "Complete one focused session" --cadence-days 1
nexus plan day --name Alex --coach-mode academic
nexus task list
nexus briefing --name Alex --weather "sunny, high 25 C"
nexus review day --name Alex
```

These local workflows do not require an API key.

## Memory, Tools, MCP, and Agents

Install optional local semantic retrieval and tool dependencies as needed:

```bash
python -m pip install -e ".[rag,tools,mcp]"
nexus config embedding set --provider fastembed --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
nexus memory reindex
nexus memory retrieve "exam preparation" --limit 5
```

FastEmbed and local Qdrant need no API key. Hosted embeddings and remote services require their own credentials.

Configure only the read-only integrations you want:

```bash
nexus config tool set weather --location "Shanghai"
nexus config tool set github --repo "example/project"
nexus config tool set filesystem --root "/path/to/project"
nexus config tool show
nexus briefing --name Alex --live-tools
nexus tool audit --limit 20
```

Configure MCP servers and approve tools explicitly:

```bash
nexus config mcp add research --transport stdio --command python --arg path/to/server.py
nexus mcp tools research
nexus config mcp policy research search ask
nexus mcp call research search --arguments '{"query":"research notes"}' --approve
nexus mcp audit --limit 20
```

Agent mode remains opt-in and bounded:

```bash
nexus plan day --agents --coach-mode startup
nexus review day --agents --coach-mode academic
nexus briefing --agents --live-tools
nexus agent runs --limit 10
```

The Tool Agent can autonomously select only enabled MCP tools whose policy is explicitly `allow`. Specialist failures fall back to the local workflow.

Expose Nexus itself to an MCP-compatible client over local stdio:

```bash
pip install -e ".[mcp]"
nexus mcp-server stdio
# Approve one ask-policy mutation for this process only:
nexus mcp-server stdio --approve-tool nexus_check_in_habit
```

The server exposes goals, memory retrieval, habits, projects, suggestions, and daily tasks as bounded read tools. Habit check-in, project progress, and suggestion acceptance default to `ask`; they run only when named with `--approve-tool` or configured as `allow` under `nexus_mcp_server.tool_policies` in `.nexus/config.local.json`.

## Proactive Runtime, Dashboard, and Automation

Runtime jobs are disabled until you opt in. Configure the three jobs, local times, and quiet hours:

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

Optional `--use-llm`, `--live-tools`, and `--agents` switches let scheduled jobs use already configured providers and permissions.

Inspect or run the scheduler:

```bash
nexus runtime status
nexus runtime tick
nexus runtime run morning_briefing
nexus runtime run evening_review
nexus runtime run stale_goal_reminders
nexus runtime start
```

A normal scheduled occurrence is claimed by `job + local date` before execution, preventing duplicate daily work after restart. `runtime run` is the explicit manual/retry path.

Every message is written to the local inbox before optional console or webhook delivery. Quiet hours defer non-urgent external delivery without losing the inbox record.

```bash
nexus notifications list --limit 20
nexus notifications flush
```

Inspect the privacy-filtered snapshot or start the dashboard:

```bash
nexus dashboard snapshot
nexus dashboard serve
# Open http://127.0.0.1:8765
```

The Dashboard has eight views. Today shows schedules, tasks, reminders, and the latest briefing/review; Habits supports check-ins, Projects supports correction-aware progress updates, Suggestions supports accept/dismiss, and Today offers replan preview/apply. Goals, eligible memory, bounded activity, and masked settings remain privacy-filtered views.

Automations are named JSON definitions. New definitions default to `ask`, which requires one-shot `--approve`.

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

Supported types are `browser`, `command`, `github_inspect`, and `status_report`. Definitions are fixed at configuration time; callers cannot append arbitrary arguments or change a target at run time.

## API Keys and Local Configuration

No API key is required for local memory, goals, planning, task updates, check-ins, deterministic briefing/review, proactive scheduling, inbox notifications, the dashboard, local sparse retrieval, FastEmbed, deterministic reports, or local browser/command automation.

Credentials are required only when the chosen feature contacts a provider that requires them:

- LLM generation, including scheduled jobs configured with `--use-llm`.
- Hosted embedding endpoints or remote Qdrant.
- External integrations that require authentication, such as Todoist, private GitHub, Notion, IMAP, or private calendar feeds. Open-Meteo and public GitHub access can work without credentials.
- Authenticated remote MCP servers.

Example LLM configuration:

```bash
nexus config llm set --provider custom --base-url "https://provider.example/v1" --api-key "<api-key>" --simple-model "<fast-model>" --complex-model "<strong-model>"
nexus config llm show
nexus briefing --llm --model-tier simple
```

Local configuration is stored in `.nexus/config.local.json`. CLI and dashboard output mask secrets. Never commit the `.nexus/` directory.

## Security Boundaries and Current Limits

- `.nexus/` contains personal state, credentials, vectors, runtime history, notifications, audits, traces, models, and lock files; Git ignores the directory as a whole.
- Shared configuration updates use an OS-backed cross-process transaction lock, validate the updated section, preserve unrelated sections, and atomically replace the file.
- State saves and notification delivery transitions also use canonical OS-backed locks. Concurrent processes cannot overwrite scheduler claims or claim the same deferred delivery; oversized corrupt notification lines are skipped and removed on rewrite.
- The dashboard is loopback-only. It validates `Host`, `Origin`, and per-process CSRF tokens; serves only exact read routes and six allowlisted action routes; rejects encoded aliases/traversal and generic mutation; bounds input/output; and isolates each snapshot section.
- The Nexus MCP Server is stdio-only and explicitly launched. Its fixed 12-tool catalog covers today context, memory search, goals, habits, projects, suggestions, replan preview, memory/goal creation, habit check-ins, project progress, and verified replan apply. Read tools are bounded; mutations default to `ask`; tool arguments/results are bounded; and audit events omit raw user content and secrets.
- Automation policies are `deny`, `ask`, and `allow`. `ask` always needs one-shot approval; unattended execution requires `allow`.
- Browser automation opens only a fixed HTTP(S) URL covered by a mandatory non-empty host allowlist.
- Command automation uses a fixed argument vector and `shell=False`. Its working directory and report paths must stay inside explicit existing roots; timeout and captured output are bounded.
- Notification and automation payloads are bounded; tool, MCP, Agent, and automation records are sanitized, and Dashboard reads expose bounded recent summaries. Corrupt JSONL lines are skipped.
- Nexus does not provide open-ended autonomy, remote dashboard hosting, arbitrary browser mutation, arbitrary LLM-authored commands, voice/vision, smart-home control, or robotics.

## CLI Command Map

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

Use `nexus <command> --help` for exact options.

## Project Documentation

- [Architecture](./docs/architecture.md)
- [Roadmap](./docs/roadmap.md)
- [AIOS task checklist](./docs/aios_task_checklist.md)
- [Project file inventory](./docs/file_inventory.md)
- [Product vision](./docs/product_vision.md)

## Development

```bash
python -m pytest tests -q
python -m ruff check src tests
python -m ruff format --check src tests
```

Update both READMEs, the checklist, and the inventory when user-facing capabilities or important files change. Never commit keys or local runtime data.

## Roadmap Summary

Phases 1-11 are implemented: CLI foundations, optional LLM generation, RAG 2.0, Planning/Reflection, real read-only integrations, MCP client and Nexus MCP Server, bounded multi-agent coordination, advanced memory lifecycle, proactive runtime, the interactive life Dashboard, permissioned named automation, habits, projects, suggestions, adaptive replanning, and unified conversation.

Next work can deepen calendar/RAG-informed suggestions and research-companion workflows. Voice, vision, smart-home, and robotics interfaces remain long-term directions built behind the same permission and audit boundaries.
