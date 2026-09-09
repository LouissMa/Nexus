# Execution Tool Contracts

Phase 15.1 now has an initial implementation in `src/nexus/execution_tools.py`.
It provides a registry and one-call dispatcher, not a model planner or task loop.

Contracts declare a unique name, description, self-contained JSON object input
and output schemas, side effects, idempotence, and optional adapter timeout.
Input schemas must reject unknown properties. Schema references are disallowed
so validation cannot fetch external resources. Contract/catalog objects are
copied to keep callers from mutating registration through a returned dictionary.

Calls validate JSON and a 16 KiB serialized input limit, check the current
manager policy, require explicit approval for ask, and invoke an adapter once.
They then validate the result against its schema and a 64 KiB serialized limit.
Failures return bounded status codes rather than copying raw exception text.
Possible statuses include success, unknown_tool, invalid_arguments, denied,
approval_required, failed, invalid_result, and result_too_large.

Effect outcome distinguishes not_started, none, unknown and
adapter_reported_success. A write followed by an exception or invalid output
has unknown effect outcome. It must not be automatically repeated. A reported
launch is still only the existing adapter's acknowledgement, not window proof.

Initial adapters are filesystem list/read/search and configured named automations.
They retain existing roots, policies and audit paths. Read defaults to 16,000
bytes and never reads the entire file before slicing. Disabled/denied tools are
omitted from the catalog and cannot be invoked through approval override.
Catalogue metadata omits stored arguments, credentials, paths and URLs.

`timeout_seconds` describes an existing adapter timeout, not a universal deadline.
The catalogue explicitly reports `not_enforced` where no adapter timeout exists.
No threads, automatic retries, scheduler, task store, or independent permission
system are added. Manager settings are checked on each invocation; local config
changes take effect when a new registry/manager is built, not via live reload.

CLI: `nexus executor tools` and `nexus executor call NAME --arguments JSON
[--approve]`. Success exits 0; unsuccessful calls exit 1; malformed configuration
or argument JSON exits 2. Arguments and approval are supplied by the caller;
there is no model-selected tool calling in this increment.

MCP, RAG, research, shared voice task state, live model planning, durable approvals,
and complete runtime evaluation are subsequent work. Do not mark Phase 15 complete.
