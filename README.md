# Nexus / LifeAgent

> **A proactive, local-first personal AI assistant with long-term memory, planning, reflection, and permissioned action.**

Nexus remembers goals and life context, creates daily plans, runs scheduled briefings and reviews, coordinates bounded specialist agents, and connects only to tools you explicitly approve.

[English](./README.md) | [Chinese](./README_zh.md)

---

## Product Direction

Phase 15.4a adds opt-in goal/RAG/research execution context. Phase 15.4b adds
shared text/voice task sessions. See the
[context design](docs/superpowers/specs/2026-09-13-execution-context-design.md).

The [shared task conversation design](docs/superpowers/specs/2026-09-14-shared-task-conversation-design.md)
describes the delivered text/voice integration (15.4b), including its foreground
and text-approval limits. Phase 15.5a now checks predeclared file conditions;
whole-goal semantic verification remains future work.

The [Phase 15.5b evaluation design](docs/superpowers/specs/2026-09-20-execution-evaluation-design.md)
is implemented: isolated offline safety regression, opt-in live-model evaluation,
durable usage metrics, JSON/Markdown reports and separate human reviews.
Offline scripted checks are not evidence of real-model task quality.

### Task Reliability Evaluation

```bash
nexus executor evaluate
nexus executor evaluate --case project-1
nexus executor evaluation-show <evaluation_id>
nexus executor evaluation-review <evaluation_id> --case project-1 --verdict partial --note "Needs a clearer limitations summary"
# Explicitly sends synthetic fixtures to your configured provider; may incur charges:
nexus executor evaluate --mode live --max-calls 12 --model-tier simple
```

Install the optional `executor` dependency first. Offline mode runs 17 packaged
synthetic cases without provider configuration or network access: nine source-reading
cases and eight safety/failure scenarios. Live mode defaults to three development
cases; variant `-3` cases are labeled holdout, not a private benchmark.
No personal RAG, automations, shell, browser or arbitrary write tools are enabled.
Each case has 8 model steps, 16 dispatches and 30 active seconds; the suite has a
cooperative 300-second deadline. In-flight calls cannot be forcibly interrupted.

Reports live under `NEXUS_HOME/evaluations/<evaluation_id>/report.json` and
`report.md`, alongside local unencrypted case databases. JSON is authoritative;
Markdown is a readable projection. Manual review notes are local user-authored text.
Model completion, source/evidence behavior, fixture file checks and human quality
judgments are separate. Zero eligible cases have a null rate, not a success rate.
Exit 0 means the evaluation finished, not that every task passed; 1 means an
incomplete/interrupted suite; 2 means invalid configuration.

Live usage comes only from individual provider responses. Missing/partial usage,
unsupported billing fields or absent pricing leave cost null. Optional `--pricing`
accepts JSON with `model`, `currency`, `effective_date`, `input_per_million` and
`output_per_million` (nonnegative decimal strings). Prices are user-supplied,
model-specific estimates, never a provider invoice. Call quota is persisted before
dispatch and unknown attempts are not refunded. This version does not resume suites.

Nexus is being built as a dependable personal AI core that understands goals, selects tools, acts on real tasks, checks results, and maintains context over time. Current execution still uses registered intents and bounded specialist workflows.

The long-term direction is a Personal AI Operating System shared by CLI, web, voice, and future embodied interfaces. The current release is not AGI: it is a local, permission-bounded assistant with explicit limits.

The next priority is **Phase 15: General Task Execution Core**: tool contracts and
open-source evaluation, a dynamic execution loop, durable tasks and approval
resume, shared context, and verified outcomes. The full stack is not yet
complete. Phase 15.1 provides tool contracts; Phase 15.2 now adds a LangGraph
foreground decision/action loop. Phase 15.3 adds local durable execution and approval
resume; 15.4 adds selected-source context and shared text/voice task entry. 15.5a adds deterministic file acceptance checks, not whole-goal verification. See the [roadmap](docs/roadmap.md) and
[capability baseline and acceptance criteria (Chinese)](docs/current_capabilities_and_next_phase.md).

## Current Features

- Long-term memory with search, semantic RAG, Qdrant persistence, re-indexing, lifecycle controls, privacy, expiry, compression, and explainable re-ranking.
- Goals, check-ins, stale-goal detection, persistent daily tasks, blockers, unresolved items, evening reflection, and four Coach modes.
- Habit tracking with daily/weekday cadence, idempotent check-ins, streaks, completion rates, and archival.
- Project tracking with linked goals/tasks, milestones, derived or explicit progress, correction history, and archival.
- Research Companion 2.0 with persistent projects, PDF/Markdown/TXT full-text corpora, chunk-level verified citations, HTTPS page acquisition, repository indexing, restricted experiments, bounded multi-Agent research loops, RAG-enriched synthesis, and explicit uncertainty.
- Explainable Suggestions 2.0 from quiet goals, blocked/pending tasks, habit risk, milestone deadlines, live calendar conflicts/focus windows, and task-relevant RAG memories, with expiring snapshots and approval-gated actions.
- Calendar-aware replan previews and stale-safe apply, with read-only live iCalendar constraints, priority allocation, shortening, and explicit unscheduled reasons.
- Unified `nexus ask` entry point with common Chinese/English local intents, approval previews for mutations, low-risk habit check-ins, and optional strict-JSON LLM intent selection.
- Explicit local Voice Assistant MVP with bounded push-to-talk recording, `faster-whisper` transcription, OS speech output, unified conversation routing, and narrated briefings.
- Voice Assistant 2.0 foreground turn-taking with WebRTC VAD, idle/turn limits, stop phrases, and temporary-audio cleanup; no wake word or speech interruption.
- Desktop Task Agent foundation: filename search, approved document opening, registered Windows app/website launch, and launch plus today's tasks through text or voice.
- Optional OpenAI-compatible LLM generation with local provider/model tiers and masked configuration.
- Read-only weather, iCalendar, Todoist, GitHub, Notion, IMAP-header, scholarly metadata, and bounded filesystem integrations.
- Permissioned MCP client over stdio or Streamable HTTP with schema discovery, deny/ask/allow policies, bounded retries, and secret-safe audits.
- Bounded Memory, Tool, Planner, Reflection, and Coach Agent coordination with budgets, fallback, and privacy-safe traces.
- Proactive morning briefing, evening review, and stale-goal reminder jobs in the user's IANA time zone.
- Durable inbox notifications, optional console/webhook delivery, and normal or overnight quiet hours.
- Responsive loopback Dashboard with Today, Goals, Habits, Projects, Research, Suggestions, Memory, Activity, and masked Settings; six exact CSRF-protected actions cover atomic habit increments, progress, suggestion decisions, and live-calendar replan preview/apply.
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

## Execution Tools (Phase 15.1)

```powershell
nexus executor tools
nexus executor call filesystem.read --arguments '{"path":"README.md","max_bytes":4000}'
nexus executor call automation.chatgpt --approve
```

Configure filesystem roots or automation aliases first. The catalog includes
enabled, permitted filesystem operations and named automations. Calls validate
input/output schemas, recheck policies, require ask-policy approval, and return
structured outcomes. Input/output limits are 16/64 KiB. There are no automatic
retries; uncertain side effects are reported explicitly. Timeout enforcement is
adapter-specific and listed in the catalog. No API key is needed for this layer.
The single-call layer is also used by the dynamic loop below. See the
[contract design](docs/superpowers/specs/2026-09-09-execution-tool-contracts.md) and
[initial open-source comparison](docs/execution_framework_evaluation.md).

## Dynamic Execution (Phases 15.2-15.3)

```powershell
pip install -e ".[executor]"
nexus executor run "Read README.md and summarize the project's current limitations" --max-steps 12 --timeout-seconds 120
```

Configure the LLM and permitted tools first. The model chooses one action at a
time, observes actual tool results and continues, asks a question or stops.
The registered allow-policy tools may execute; ask-policy tools stop with a
pending approval. Approvals are single-use and bound to the run, action and tool configuration.
Tool data may be sent to the configured LLM. LangSmith tracing is disabled.
The deadline is checked between steps and passed to model calls; existing tool
timeouts still apply and are not universally preemptive.

`reported_complete` means the model supplied successful tool references, not
independently verified task success. Other outcomes distinguish approval/input
waits, budgets, failure, repetition and uncertain side effects. CLI runs are saved
in `NEXUS_HOME/executor.sqlite3` (default `.nexus/executor.sqlite3`). Use `resume`,
not another `run`, to continue the same task. Selected-source RAG context is
available below; shared text/voice entry is also available. General MCP execution adapters remain subsequent work.

```powershell
nexus executor runs
nexus executor show RUN_ID
nexus executor resume RUN_ID --approval-token TOKEN_FROM_SHOW
nexus executor resume RUN_ID --answer "Use the project folder"
nexus executor pause RUN_ID
nexus executor resume RUN_ID
nexus executor cancel RUN_ID
```

Inspect the pending tool and arguments before approving. Configuration changes
invalidate the token; inspect again for a new token. Listing, viewing, control
requests and reconciliation need no API key. Resume needs a configured model.
Pause/cancel are cooperative requests checked at execution boundaries, not OS
process termination. Cancellation is sticky. Step and active-time budgets are
retained across resumes; waiting for a person does not consume the time budget.
An exhausted budget is not automatically renewed.

If a process exits during a tool call, resume reports `needs_review` and refuses
automatic replay. After independently checking the destination, record one outcome:

```powershell
nexus executor resolve RUN_ID --outcome completed --note "Verified the destination manually"
# OR, only after confirming no operation occurred:
nexus executor resolve RUN_ID --outcome not-executed --note "Confirmed the destination was unchanged"
```

Reconciliation never calls tools and is recorded as user evidence, not tool success.
It leaves the task paused (or cancelled); a later resume can continue, with fresh
approval where required. Partial or unknown effects must remain unresolved until
checked. This is conservative recovery, not an exactly-once execution guarantee.
Snapshots contain local goal/answer/tool data, are not encrypted, and must not be
published; provider keys/configurations are not copied into the task store.
See the [durable execution design](docs/superpowers/specs/2026-09-12-durable-execution.md).

## Execution Context (Phase 15.4a)

Context is opt-in; existing commands without these options are unchanged.
Replace the example IDs with your own goal and research project IDs:

```powershell
nexus executor run "Review my next research step" --with-context --context-goal GOAL_ID --context-research RESEARCH_ID
nexus executor run "Plan a focused study step" --with-context --context-memory-scope private --allow-sensitive-context
```

Selected goal/research fields and relevant memories may be sent to your configured
LLM. Default memory scope is `shared`; `personal` or `private` requires explicit
`--allow-sensitive-context`. This does not widen tool permissions. Configured RAG
may send the task query to an embedding provider; no automatic re-index or extra
LLM summarization call is added.

Limits: three unique selected goals, five relevant memories, one selected research
project, five open questions, 1,000 characters per text field and 16 KiB of UTF-8
JSON overall. Research context includes its objective/questions/counts, not full
papers, notes or experimental output. `executor show RUN_ID` includes provenance,
retrieval strategy/scores, truncation and safe degradation codes.

Resume reuses the saved context rather than retrieving again. Removed, expired,
archived, privacy-changed or edited referenced sources block continuation with
`context_invalid`, preserving pending approvals. Validation also runs before each
model/tool step. There is no automatic refresh or restart; do not rerun a task
blindly if it may already have produced side effects. These checks cannot recall
data already sent to a provider or erase historical plaintext run snapshots.
Context references never count as successful tool evidence.

## File Acceptance Checks (Phase 15.5a)

Declare checks before execution with `executor run --acceptance`. Conditions are
fixed in the run and shown to the model, including paths and expected strings.
They do not grant filesystem permissions. Replace the example with a file inside
your configured read roots; this example checks an existing document, not creation:

```powershell
$acceptance = @{checks=@(@{path='D:/Projects/example/README.md';kind='nonempty'})} | ConvertTo-Json -Depth 5 -Compress
nexus executor run "Read the project README and summarize its limitations" --acceptance $acceptance
nexus executor verify RUN_ID
nexus ask "show progress" --task-mode --task-id RUN_ID
```

Supported kinds: `exists` (successful regular-file read), `nonempty`, `contains`
(add `value`), and `json_fields` (add `fields`, for example `{"title":"string","count":"integer"}`).
JSON checks cover top-level field types, not arbitrary schemas. Checks run locally
after the model reports completion; explicit `verify` rechecks without an LLM or
replaying any execution steps. Contract fields cannot be changed through resume.
Task-mode start does not yet accept checks; create with executor and select that run.

The lifecycle stays `reported_complete`; `verification_report.status` separately
reports `passed`, `partial`, `failed` or `unverifiable`, with time and per-check
reasons. All-pass means only the declared conditions held at check time, not that
Nexus created the file or achieved the entire goal. Later changes can invalidate
the result. Runs without a contract preserve the previous unverified-completion behavior.
Run/resume/verify exit nonzero when declared checks do not all pass.

Bounds: 1-20 checks, 16 KiB contract, 16,000-byte reads and a cooperative five-second
check budget (not a hard timeout for an in-flight read). Denied, missing/unreadable,
truncated or decoding-uncertain inputs are not declared successful. Reports retain
no raw contents; local criteria/paths remain plaintext. Speech projects only check
status/counts/time. Up to ten prior reports survive rechecks. Interrupted checking
is marked pending and can be repeated with `verify`; side effects are never replayed.

Acceptance-bearing clarification questions are text-only as well, including the
first question before any tool call, because the model may repeat private criteria.

## Shared Task Conversation (Phase 15.4b)

Task mode connects text and voice to the same durable run. Ordinary conversation
is unchanged. Use an explicit start request to execute a new goal:

```powershell
nexus ask "start task: Read the project README and summarize its limitations" --task-mode
nexus ask "show progress" --task-mode
nexus voice chat --task-mode
nexus ask "answer: use the project folder" --task-mode
nexus ask "continue task" --task-mode
```

Both interfaces use local session `default`; set `--task-session research` on
both to separate workflows. A session remembers its selected run after restart.
These names are local labels, not authenticated users or privacy boundaries.
Select a run created with the executor, including one with context:

```powershell
nexus ask "show progress" --task-mode --task-id RUN_ID
nexus ask "list tasks" --task-mode
nexus ask "select task 2 @REVISION" --task-mode
nexus ask "pause task" --task-mode
nexus ask "cancel task" --task-mode
```

Without a selection, Nexus shows at most five candidates and asks you to choose;
it never guesses the newest run. Numbered selection refers to the saved candidate
list. Replace REVISION with selection_revision returned by the list command.
A new CLI process requires this receipt (or the full run ID); a continuous voice
session can use a bare number from its own displayed list. Stale receipts are
rejected if another interface refreshes or changes the selection. An in-flight
request retains its resolved run ID even if another interface changes selection.
A selection conflict during task creation can leave an unexecuted `created` run
visible in the task list; it does not invoke tools or silently retry.

Lifecycle controls use deterministic Chinese/English phrases; arbitrary chat
does not start a task. A non-control reply answers a selected task only while it
is waiting_input. New tasks are context-free; select an explicitly configured
15.4a run to continue with its existing context and consent.

Progress, selection and pause/cancel require no LLM or Embedding initialization.
Idle cancellation is acknowledged under the run lease without model calls;
active calls remain cooperative, and uncertain tool outcomes still require review.
Questions after tool observations or attached context stay in the text view;
speech asks the user to read and answer, rather than repeating potentially private data.
Execution requires a configured model and retains existing budgets/permissions.
`--approve` is rejected in task mode. Spoken or typed "yes" never approves a tool:
inspect `executor show RUN_ID`, then approve with its exact token via
`executor resume RUN_ID --approval-token TOKEN`. Task-mode voice can stay open
for status/control while approval waits; ordinary voice still stops on approval.
Speech omits approval tokens and raw tool results, and distinguishes waiting,
failure and model-reported completion from independently verified success.

This is foreground turn-taking, not background execution or speech interruption.
While a tool/model call blocks, this microphone loop cannot listen for "stop";
another text process can request cooperative cancellation. Automated tests use
fake audio and scripted models, not real microphone/recognition acceptance tests.

## Desktop Tasks

The Desktop Task Agent foundation connects text and voice to authorized filename
search and registered application/website launch. Configure your own existing
folder (replace the example path), then register the included ChatGPT website:

```powershell
nexus config tool set filesystem --root "D:/Pictures"
nexus automation set chatgpt --definition (Get-Content -Raw examples/desktop-chatgpt.json)
nexus ask "find files passport"
nexus ask "open chatgpt"
nexus ask "open chatgpt" --approve
nexus ask "open file D:/Pictures/passport.jpg" --approve
nexus ask "Hi Nexus，帮我打开Chatgpt，我们开始今天的任务" --approve
```

Filename search includes images and returns numbered paths, size, modification
time, and truncation status. `护照照片` also matches `passport` filenames. Each
root scan is bounded to 10,000 entries, 50 matches and five seconds; at most ten
configured roots are visited. Hidden entries, links and junctions are skipped.
Randomly named photos cannot yet be identified by image content; there is no OCR
or thumbnail interface in this increment.

Inside one `voice chat` session, `open result 2` or `打开第二张` refers to the latest
search. File opening requires a one-shot approval and authorized filesystem read
access; only common image, PDF, TXT and Markdown files are supported. The voice
session stops at an approval preview; use its explicit path with `nexus ask ...
--approve` to execute. Candidate numbers do not persist across CLI invocations.

Register a Windows desktop app with `nexus automation set <alias> --definition`
and an object such as `{"type":"application","executable":"C:/Apps/Example/app.exe","policy":"ask"}`,
using an actual existing absolute `.exe` path. Applications take no caller-supplied
arguments. Registered browser/application policies remain deny/ask/allow; an
explicitly trusted `allow` alias can launch during voice chat without stopping
for approval. `Hi Nexus` is an optional text prefix, not a wake word.

Opening reports that the OS accepted a launch request; it does not verify the
window, log in, click controls, or execute today's tasks. Local file/app opening
currently targets Windows; website opening uses the existing browser adapter.
The work-start phrase opens the registered alias and lists today's tasks. No
OpenClaw code or runtime dependency is included.

## Local Voice Assistant

Text-only Nexus continues to work without voice dependencies or an API key. Install the optional voice dependencies only when you want explicit local recording, transcription, or speech:

```bash
pip install -e ".[voice]"
nexus config voice set --enable --model small --language auto
nexus voice ask --record-seconds 5
nexus voice chat --max-turns 20 --idle-seconds 30
nexus voice briefing --live-tools
```

`nexus voice ask` records for the requested bounded duration, transcribes the WAV locally, routes the transcript through the same conversation and approval path as `nexus ask`, and uses operating-system speech when available. `nexus voice briefing` reuses the existing text briefing, including explicitly requested live tools. Use `nexus voice status`, `nexus voice record`, `nexus voice transcribe`, and `nexus voice speak` for diagnostics or individual operations.

`nexus voice chat` starts Voice Assistant 2.0 continuous turn-taking: WebRTC VAD waits for speech and ends each utterance after about 900 ms of silence. Nexus processes and speaks the reply, then listens again. Say `end conversation` or `结束对话`, press Ctrl+C, or wait for the idle timeout to exit. Pending approvals stop ordinary sessions with a preview; explicit task-mode sessions can continue safe status/control turns without approving. Approvals never carry across turns. `--no-play` returns text without speech. Output is flushed JSON-line session events. The default limit is 20 capture attempts (maximum 100); idle timeout defaults to 30 seconds (maximum 120). Empty transcriptions consume an attempt and resume listening.

Reinstall `pip install -e ".[voice]"` when upgrading to obtain `webrtcvad-wheels`. Audio remains local and temporary recordings are deleted. Whisper may download its model on first use. Add `--llm` to use the configured text LLM for existing intent parsing; transcribed text may then be sent to that provider. Sessions reuse the command router, without new conversational history or pronoun resolution. Listening pauses during processing/playback. Wake words, speech interruption, background listening, and Dashboard microphone access remain future work.

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
nexus suggestion refresh --live-tools
nexus suggestion list
nexus tool audit --limit 20
```

Suggestion refresh always uses the configured RAG pipeline. `--live-tools` additionally reads the configured calendar; either dependency can degrade independently while local goal/task/habit/project suggestions remain available. The optional LLM may rewrite wording only.

## Research Companion

Create an evidence-oriented research workspace and record sources, notes, and experiments:

```bash
nexus research create "RAG evaluation" --objective "Compare dense and hybrid retrieval" --question "What improves recall?"
nexus research source-add <research-id> --type paper --title "Hybrid retrieval study" --locator "https://doi.org/..." --note "Reported a recall improvement"
nexus research note-add <research-id> "The benchmark gain needs replication" --source-id <source-id> --tag evaluation
nexus research experiment-add <research-id> "Dense versus hybrid" --hypothesis "Hybrid improves recall" --method "Compare twenty queries" --result "Hybrid recovered two more memories" --status completed
```

Local synthesis and follow-up answers use eligible RAG memory and do not require an API key:

```bash
nexus research synthesize <research-id>
nexus research ask <research-id> "Did hybrid retrieval improve recall?"
nexus research list
nexus ask "list research"
```

Install optional PDF support, then build a project corpus from explicit local files, HTTPS pages, or repositories:

```bash
python -m pip install -e ".[research]"
nexus research document-add <research-id> ./paper.pdf
nexus research document-add <research-id> ./notes.md
nexus research web-add <research-id> https://example.org/article
nexus research repo-index <research-id> ./my-repository
nexus research document-list <research-id>
nexus research document-search <research-id> "hybrid retrieval recall"
nexus research run <research-id> "Does hybrid retrieval improve recall?" --max-cycles 3
```

PDF references preserve page numbers; text, web, and repository references preserve line ranges. `document-show`, `document-remove`, and `document-reindex` manage the corpus. Identical content is not indexed twice, failed re-indexing preserves the last valid index, and every returned document reference is checked against its stored chunk hash.

Explicitly approved experiments use an argument vector, executable allowlist, allowed working root, timeout, minimal environment, `shell=False`, and capped output:

```bash
nexus research experiment-run <research-id> --cwd ./experiment --allowed-root ./experiment --allow-executable python --approve --command python evaluate.py
```

This is a restricted process runner, not a kernel or container sandbox. Research loops never fetch pages or execute commands implicitly.

Enable bounded scholarly metadata search explicitly when needed:

```bash
nexus config tool set literature --mailto "researcher@example.com"
nexus tool literature --query "retrieval augmented generation evaluation" --limit 5
nexus research investigate <research-id> --query "hybrid retrieval evaluation" --live-tools
```

The `literature` adapter uses only Crossref's fixed read-only `/works` endpoint and imports bounded bibliographic metadata; it does not download or read full papers. `--llm --model-tier complex` can rewrite synthesis or follow-up wording, but exact evidence references and uncertainty remain deterministic. Literature, RAG, and LLM failures degrade independently.

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

The Dashboard has nine views. Today shows schedules, tasks, reminders, and the latest briefing/review; Habits supports check-ins, Projects supports correction-aware progress updates, Research shows bounded questions, source/experiment counts, and the latest synthesis, Suggestions shows Calendar/RAG source types and degradation status before accept/dismiss, and Today offers replan preview/apply. Goals, eligible memory, bounded activity, and masked settings remain privacy-filtered views.

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

No API key is required for local memory, goals, planning, task updates, check-ins, deterministic briefing/review, proactive scheduling, inbox notifications, the dashboard, local sparse retrieval, FastEmbed, deterministic reports, local browser/command automation, or the initial local voice path.

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
- Research Companion does not perform OCR, JavaScript-rendered browsing, authenticated crawling, arbitrary shell execution, container isolation, or unbounded background research. Web acquisition requires an explicit HTTPS URL; the restricted experiment runner is not an OS sandbox.
- Voice recording is explicit and duration-bounded. Continuous turn-taking runs only during `voice chat`; wake words, speaker identification, speech interruption, and Dashboard microphone access are not implemented.
- Nexus does not provide open-ended autonomy, remote dashboard hosting, arbitrary browser mutation, arbitrary LLM-authored commands, visual context, smart-home control, or robotics.

## CLI Command Map

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

Phases 1-12 and Research Companion 2.0 are implemented. Phase 13 includes the Voice Assistant MVP and Voice Assistant 2.0 continuous foreground turn-taking. Wake words, interruption, visual context, and embodied interfaces remain future work.

Continuous listening and wake words, visual context, family profiles, smart-home adapters, and robotics remain future work behind the same permission and audit boundaries.
