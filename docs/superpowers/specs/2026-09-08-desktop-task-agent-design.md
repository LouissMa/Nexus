# Desktop Task Agent Foundation

This increment connects explicit desktop tasks to the existing text and voice
conversation router. It supports filename search, approved document opening,
registered application/website launch, and launch plus today's task listing.

## Boundaries

- Filename search reuses the filesystem tool's `search` permission and audit.
  It searches configured roots only, skips hidden entries and links/junctions,
  and never reads image contents. Each root scan caps at 10,000 entries, 50
  results, and five seconds; at most ten roots are searched. Results include
  names, paths, size, modification time, and explicit truncation.
- Opening a document requires filesystem `read` permission and one-shot approval.
  Only common image, PDF, TXT, and Markdown extensions within roots are allowed.
  This delegates to the Windows file association and does not sandbox the viewer.
- Applications use named `application` automations with an existing absolute
  `.exe` path and no model-supplied arguments. Existing automation enablement,
  deny/ask/allow rules and audits remain in effect. Websites use existing browser
  automations. No implicit application discovery or website registration occurs.
- Candidate numbers refer to the latest search in one ConversationService
  instance, including a running voice session. They are not persisted across CLI
  invocations. Approval previews resolve a candidate to its explicit path.
- A successful launch means the OS accepted the request, not that a window or
  website content was inspected. The work-start intent attaches today's tasks;
  it does not execute those tasks or open an inferred project.
- Voice retains its current approval-stop behavior. Trusted application aliases
  configured with allow can launch inside a continuous voice session. The words
  Hi Nexus can prefix an explicit request but do not constitute a wake word.

## Deferred

OCR, image embeddings, thumbnail UI, desktop UI interaction, application
discovery, general task planning/retries, arbitrary commands, and OpenClaw code
integration remain future increments. No OpenClaw code is copied in this phase.

## Verification

Test filename-vs-content behavior, directory boundaries, disabled permissions,
candidate resolution, app policies, exact executable validation, local and LLM
intent routes, voice composition, and startup-result semantics. Use injected
openers so tests do not launch user applications or access personal documents.
