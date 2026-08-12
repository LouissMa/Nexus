from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4
import re

from .research import ResearchService
from .research_corpus import ResearchCorpus
from .store import JsonStore


class ResearchLoopError(ValueError):
    pass


class ResearchLoop:
    def __init__(
        self,
        store: JsonStore,
        research: ResearchService,
        corpus: ResearchCorpus,
        *,
        memory_search: Any = None,
        llm: Any = None,
    ) -> None:
        self.store = store
        self.research = research
        self.corpus = corpus
        self.memory_search = memory_search
        self.llm = llm

    def run(
        self,
        project_id: str,
        question: str,
        *,
        max_cycles: int = 3,
        use_llm: bool = False,
        now: datetime | None = None,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        clean_question = str(question).strip()
        if not clean_question:
            raise ResearchLoopError("Research question is required.")
        cycles_budget = max(1, min(int(max_cycles), 5))
        deadline = monotonic() + max(1.0, min(float(timeout_seconds), 120.0))
        self.research.show(project_id)
        trace: list[dict[str, Any]] = []
        degradations: list[str] = []
        findings: list[dict[str, Any]] = []
        terminal_reason = "needs_evidence"
        cycles = 0
        for cycle in range(1, cycles_budget + 1):
            if monotonic() >= deadline:
                terminal_reason = "budget_exhausted"
                break
            cycles = cycle
            trace.append(
                self._step(
                    "planner",
                    "completed",
                    {"cycle": cycle, "question": clean_question[:300]},
                )
            )
            try:
                chunks = self.corpus.search(project_id, clean_question, limit=8)
                retrieval_status = "completed"
            except Exception:
                chunks = []
                retrieval_status = "degraded"
                if "corpus_unavailable" not in degradations:
                    degradations.append("corpus_unavailable")
            trace.append(
                self._step("retriever", retrieval_status, {"result_count": len(chunks)})
            )
            candidates = [
                {
                    "text": str(item.get("text", ""))[:1_200],
                    "references": [str(item["reference"])],
                    "uncertainty": "supported",
                }
                for item in chunks[:5]
                if item.get("reference") and item.get("text")
            ]
            trace.append(
                self._step("analyst", "completed", {"finding_count": len(candidates)})
            )
            verified = []
            rejected = 0
            question_terms = self._terms(clean_question)
            for candidate in candidates:
                references = candidate["references"]
                evidence_terms = self._terms(candidate["text"])
                relevant = bool(question_terms.intersection(evidence_terms))
                if relevant and all(
                    self.corpus.validate_reference(ref).get("valid")
                    for ref in references
                ):
                    verified.append(candidate)
                else:
                    rejected += 1
            trace.append(
                self._step(
                    "critic",
                    "completed",
                    {"accepted": len(verified), "rejected": rejected},
                )
            )
            findings = verified
            if findings:
                terminal_reason = "complete"
            trace.append(
                self._step(
                    "reflection", "completed", {"terminal_reason": terminal_reason}
                )
            )
            if terminal_reason == "complete" or not chunks:
                break
        timestamp = (
            (now or datetime.now(UTC))
            .astimezone(UTC)
            .replace(microsecond=0)
            .isoformat()
        )
        result = {
            "id": uuid4().hex[:12],
            "project_id": project_id,
            "question": clean_question[:1_000],
            "status": "completed" if terminal_reason == "complete" else "partial",
            "terminal_reason": terminal_reason,
            "cycles": cycles,
            "findings": findings,
            "open_questions": [] if findings else [clean_question[:1_000]],
            "next_actions": (
                ["Review verified findings and design a bounded validation experiment."]
                if findings
                else [
                    "Acquire a relevant document or web source, then run the research loop again."
                ]
            ),
            "degradations": degradations,
            "trace": trace,
            "llm": {"requested": bool(use_llm), "used": False},
            "created_at": timestamp,
        }
        return self._persist(project_id, result)

    def _persist(self, project_id: str, result: dict[str, Any]) -> dict[str, Any]:
        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            for project in state.get("research_projects", []):
                if isinstance(project, dict) and project.get("id") == project_id:
                    history = project.setdefault("research_runs", [])
                    history.append(deepcopy(result))
                    del history[:-50]
                    project["updated_at"] = result["created_at"]
                    return deepcopy(result)
            raise ResearchLoopError(f"Research project '{project_id}' not found.")

        return self.store.mutate(mutation)

    @staticmethod
    def _step(agent: str, status: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"agent": agent, "status": status, "metadata": metadata}

    @staticmethod
    def _terms(text: str) -> set[str]:
        stop = {
            "the",
            "a",
            "an",
            "is",
            "was",
            "what",
            "does",
            "did",
            "and",
            "or",
            "to",
            "of",
            "in",
            "on",
        }
        terms: set[str] = set()
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.casefold()):
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                terms.update(
                    token[index : index + 2] for index in range(len(token) - 1)
                )
            elif len(token) > 2 and token not in stop:
                terms.add(token)
        return terms
