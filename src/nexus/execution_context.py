from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime

from nexus.memory_lifecycle import is_memory_eligible, parse_memory_time
from nexus.research import research_summary


MAX_CONTEXT_BYTES = 16384


class ExecutionContextError(ValueError):
    """Safe user-facing context failure without source/provider error text."""


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_context_options(*, goal_ids=(), research_id=None, memory_scope="shared", allow_sensitive=False):
    if memory_scope not in {"shared", "personal", "private"}:
        raise ExecutionContextError("Invalid context memory scope.")
    if type(allow_sensitive) is not bool or (memory_scope != "shared" and not allow_sensitive):
        raise ExecutionContextError("Sensitive context requires explicit consent.")
    if not isinstance(goal_ids, (list, tuple)) or len(goal_ids) > 3 or len(set(goal_ids)) != len(goal_ids):
        raise ExecutionContextError("Select at most three unique context goals.")
    for value in [*goal_ids, *([research_id] if research_id is not None else [])]:
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise ExecutionContextError("Invalid context source ID.")


class ExecutionContextBuilder:
    def __init__(self, service, *, retriever_factory=None, clock=None):
        self.service = service
        self.retriever_factory = retriever_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def _eligible(self, raw, scope):
        now = self.clock()
        expires = parse_memory_time(raw.get("expires_at"), "expires_at")
        return (not expires or expires > now) and is_memory_eligible(raw, privacy=scope, now=now)

    @staticmethod
    def _project(kind, raw):
        if kind == "memory":
            return {"id": raw["id"], "text": raw.get("text", ""), "tags": raw.get("tags", [])[:8],
                    "privacy": raw.get("privacy", "private"), "status": raw.get("status", "active"),
                    "expires_at": raw.get("expires_at"), "pinned": raw.get("pinned", False)}
        if raw.get("status", "active") == "archived":
            raise ExecutionContextError("Selected context source is archived.")
        if kind == "goal":
            return {key: raw.get(key) for key in ("id", "title", "description", "status", "cadence_days", "last_check_in")}
        if kind == "research":
            return {"id": raw["id"], "title": raw.get("title", ""), "objective": raw.get("objective", ""),
                    "status": raw.get("status", "active"), "summary": research_summary(raw),
                    "questions": [{"id": q["id"], "text": q.get("text", ""), "status": "open"}
                                  for q in raw.get("questions", []) if q.get("status") == "open"][:5]}
        raise ExecutionContextError("Invalid context source kind.")

    @staticmethod
    def _sources(state):
        return {kind: {item["id"]: item for item in state.get(key, [])}
                for kind, key in (("goal", "goals"), ("memory", "memories"), ("research", "research_projects"))}

    def build(self, goal, *, goal_ids=(), research_id=None, memory_scope="shared", allow_sensitive=False):
        validate_context_options(goal_ids=goal_ids, research_id=research_id,
                                 memory_scope=memory_scope, allow_sensitive=allow_sensitive)
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 4000:
            raise ExecutionContextError("Invalid context query.")
        sources = self._sources(self.service.store.load())
        context = {"version": 1, "policy": {"memory_scope": memory_scope, "allow_sensitive": allow_sensitive},
                   "captured_at": self.clock().isoformat(), "goals": [], "memories": [], "research": None,
                   "references": [], "degradations": [], "truncated": False}

        def select(kind, source_id):
            raw = sources[kind].get(source_id)
            if raw is None:
                raise ExecutionContextError("Selected context source does not exist.")
            projection = self._project(kind, raw)
            context["references"].append({"kind": kind, "id": source_id, "digest": _digest(projection)})
            return projection

        context["goals"] = [select("goal", key) for key in goal_ids]
        if research_id is not None:
            context["research"] = select("research", research_id)
        try:
            eligible = [raw for raw in sources["memory"].values() if self._eligible(raw, memory_scope)]
            retriever = self.retriever_factory() if self.retriever_factory else self.service.memory_retriever
            result = retriever.retrieve_result(eligible, goal, 5, privacy=memory_scope, task_context=goal, now=self.clock())
            strategy = result.metadata.get("strategy")
            strategy = strategy if strategy in {"hybrid_dense_sparse", "local_sparse_embedding"} else "other"
            memories = []
            seen = set()
            for hit in result.memories:
                key = hit.get("memory_id") or hit.get("id")
                raw = sources["memory"].get(key)
                if key in seen or raw is None or not self._eligible(raw, memory_scope):
                    continue
                score = float(hit.get("retrieval_score", 0))
                if not math.isfinite(score):
                    continue
                seen.add(key)
                memories.append({**self._project("memory", raw), "retrieval": {"strategy": strategy, "score": score}})
                if len(memories) == 5:
                    break
            context["memories"] = memories
            for item in memories:
                select("memory", item["id"])
            if result.metadata.get("error"):
                context["degradations"].append("memory_dense_unavailable")
        except (ValueError, TypeError, KeyError, RuntimeError, OSError):
            context["memories"] = []
            context["references"] = [r for r in context["references"] if r["kind"] != "memory"]
            context["degradations"] = ["memory_retrieval_unavailable"]

        def clip(value):
            if isinstance(value, str) and len(value) > 1000:
                context["truncated"] = True
                return value[:1000]
            if isinstance(value, dict):
                return {k: clip(v) for k, v in value.items()}
            if isinstance(value, list):
                return [clip(v) for v in value]
            return value

        for key in ("goals", "memories", "research"):
            context[key] = clip(context[key])
        while len(_encoded(context)) > MAX_CONTEXT_BYTES:
            context["truncated"] = True
            if context["memories"]:
                removed = context["memories"].pop()
                context["references"] = [r for r in context["references"]
                                         if not (r["kind"] == "memory" and r["id"] == removed["id"])]
            elif context["research"] and context["research"]["questions"]:
                context["research"]["questions"].pop()
            else:
                descriptions = [item for item in context["goals"] if item.get("description")]
                if descriptions:
                    descriptions[-1]["description"] = ""
                elif context["research"] and context["research"].get("objective"):
                    context["research"]["objective"] = ""
                else:
                    raise ExecutionContextError("Minimal context exceeds 16 KiB.")
        return context

    def validate(self, context):
        try:
            if context["version"] != 1 or len(_encoded(context)) > MAX_CONTEXT_BYTES:
                raise ValueError
            policy = context["policy"]
            validate_context_options(memory_scope=policy["memory_scope"], allow_sensitive=policy["allow_sensitive"])
            sources = self._sources(self.service.store.load())
            for reference in context["references"]:
                kind, key = reference["kind"], reference["id"]
                raw = sources[kind][key]
                if kind == "memory" and not self._eligible(raw, policy["memory_scope"]):
                    raise ValueError
                if _digest(self._project(kind, raw)) != reference["digest"]:
                    raise ValueError
        except (ValueError, TypeError, KeyError, RuntimeError, OSError):
            raise ExecutionContextError("Execution context is stale or unavailable; continuation blocked.") from None
