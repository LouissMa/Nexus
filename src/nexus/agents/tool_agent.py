from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from jsonschema import SchemaError
from jsonschema.validators import validator_for

from nexus.llm import LLMError, OpenAICompatibleLLM
from nexus.mcp.models import MCPError

from .models import AgentBudgetExceeded, AgentResult, AgentRunContext

if TYPE_CHECKING:
    from nexus.mcp.manager import MCPManager
    from nexus.service import BriefingLLM


class ToolAgent:
    name = "tool"

    def __init__(
        self,
        manager: MCPManager,
        *,
        llm: BriefingLLM | None = None,
    ):
        self.manager = manager
        self.llm = llm

    def run(self, context: AgentRunContext) -> AgentResult:
        candidates = self.manager.agent_candidates(
            timeout_provider=context.budget.remaining_seconds
        )
        context.budget.check_time()
        errors = list(candidates.get("errors", []))
        tools = candidates.get("tools", [])
        selected: list[dict[str, Any]] = []

        bound = [
            {
                "server": tool["server"],
                "tool": tool["tool"],
                "arguments": tool["bound_arguments"],
                "schema": tool["input_schema"],
            }
            for tool in tools
            if tool.get("bound_arguments") is not None
        ]
        if bound:
            selected = bound
        elif context.use_llm and self.llm is not None and tools:
            try:
                context.budget.consume_llm()
                selected = self._select_with_llm(context, tools)
            except (AgentBudgetExceeded, LLMError, ValueError) as exc:
                errors.append({"error": str(exc)})
        elif context.use_llm and self.llm is None and tools:
            errors.append({"error": "LLM client is not configured for tool selection."})

        results: list[dict[str, Any]] = []
        selected_metadata: list[dict[str, Any]] = []
        for call in selected:
            try:
                self._validate_arguments(call["arguments"], call["schema"])
                context.budget.consume_tool()
                result = self.manager.call(
                    call["server"],
                    call["tool"],
                    call["arguments"],
                    timeout_seconds=context.budget.remaining_seconds(),
                )
                results.append({"server": call["server"], **result.to_dict()})
                selected_metadata.append(
                    {
                        "server": call["server"],
                        "tool": call["tool"],
                        "argument_keys": sorted(call["arguments"]),
                    }
                )
            except (AgentBudgetExceeded, MCPError, ValueError) as exc:
                errors.append(
                    {
                        "server": call["server"],
                        "tool": call["tool"],
                        "error": str(exc),
                    }
                )

        if errors and results:
            status = "partial"
        elif errors:
            status = "fallback"
        else:
            status = "completed"
        return AgentResult(
            agent=self.name,
            status=status,
            summary=f"Called {len(results)} approved MCP tools.",
            artifact={"results": results, "errors": errors},
            metadata={
                "candidate_count": len(tools),
                "selected_tools": selected_metadata,
                "error_count": len(errors),
            },
            error="tool_agent_error" if errors and not results else None,
        )

    def _select_with_llm(
        self,
        context: AgentRunContext,
        tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        public_tools = [
            {
                "server": item["server"],
                "tool": item["tool"],
                "description": item.get("description"),
                "input_schema": item.get("input_schema", {}),
            }
            for item in tools
        ]
        raw = self._generate_llm(
            context,
            (
                "Select zero or more tools for Nexus. Return JSON only as "
                '{"calls":[{"server":"...","tool":"...","arguments":{}}]}. '
                "Use only listed tools and satisfy each input schema."
            ),
            (
                f"Task: {context.inputs.get('query', context.workflow)}\n"
                f"Allowed tools: {json.dumps(public_tools, ensure_ascii=False)}"
            ),
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Tool selection returned invalid JSON.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("calls"), list):
            raise ValueError("Tool selection JSON must contain a calls array.")

        by_name = {(item["server"], item["tool"]): item for item in tools}
        selected: list[dict[str, Any]] = []
        for call in payload["calls"]:
            if not isinstance(call, dict):
                raise ValueError("Each selected tool call must be an object.")
            server = call.get("server")
            tool = call.get("tool")
            arguments = call.get("arguments", {})
            candidate = by_name.get((server, tool))
            if candidate is None:
                raise ValueError(
                    f"Tool selection rejected unknown or unapproved tool '{server}/{tool}'."
                )
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
            self._validate_arguments(arguments, candidate.get("input_schema", {}))
            selected.append(
                {
                    "server": server,
                    "tool": tool,
                    "arguments": arguments,
                    "schema": candidate.get("input_schema", {}),
                }
            )
        return selected

    def _generate_llm(
        self,
        context: AgentRunContext,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if isinstance(self.llm, OpenAICompatibleLLM):
            return self.llm.generate(
                system_prompt,
                user_prompt,
                timeout_seconds=context.budget.remaining_seconds(),
            )
        return self.llm.generate(system_prompt, user_prompt)

    @staticmethod
    def _validate_arguments(
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> None:
        try:
            validator_class = validator_for(schema)
            validator_class.check_schema(schema)
        except SchemaError as exc:
            raise ValueError(
                f"MCP tool published an invalid input schema: {exc.message}."
            ) from exc

        errors = sorted(
            validator_class(schema).iter_errors(arguments),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        if errors:
            error = errors[0]
            path = ".".join(str(part) for part in error.absolute_path)
            location = f" at '{path}'" if path else ""
            raise ValueError(
                f"Tool arguments failed schema validation{location}: {error.message}."
            )
