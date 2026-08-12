from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import re
from typing import Any
from uuid import uuid4

from .store import JsonStore


SOURCE_TYPES = ("paper", "web", "book", "code", "dataset", "other")
EXPERIMENT_STATUSES = ("planned", "running", "completed", "blocked")
MAX_PROJECTS = 100
MAX_ITEMS = 500
MAX_TEXT_LENGTH = 4_000
MAX_LOCATOR_LENGTH = 2_000


class ResearchError(ValueError):
    pass


def _timestamp(value: datetime | None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).replace(microsecond=0).isoformat()


def _text(
    value: str,
    field: str,
    *,
    required: bool = False,
    limit: int = MAX_TEXT_LENGTH,
) -> str:
    result = str(value).strip()
    if required and not result:
        raise ResearchError(f"{field} is required.")
    if len(result) > limit:
        raise ResearchError(f"{field} must be at most {limit} characters.")
    return result


def _unique(values: list[str] | tuple[str, ...], limit: int = 100) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = str(raw).strip()[:100]
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def research_summary(project: dict[str, Any]) -> dict[str, int]:
    return {
        "question_count": len(project.get("questions", [])),
        "source_count": len(project.get("sources", [])),
        "note_count": len(project.get("notes", [])),
        "experiment_count": len(project.get("experiments", [])),
        "investigation_count": len(project.get("investigations", [])),
        "synthesis_count": len(project.get("syntheses", [])),
        "follow_up_count": len(project.get("follow_ups", [])),
        "document_count": len(project.get("documents", [])),
        "research_run_count": len(project.get("research_runs", [])),
    }


class ResearchService:
    def __init__(
        self,
        store: JsonStore,
        retriever: Any = None,
        llm: Any = None,
        corpus_search: Any = None,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.llm = llm
        self.corpus_search = corpus_search

    def create(
        self,
        title: str,
        objective: str,
        question: str = "",
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)
        initial_question = _text(question, "question")
        project = {
            "id": uuid4().hex[:8],
            "title": _text(title, "title", required=True),
            "objective": _text(objective, "objective"),
            "status": "active",
            "questions": [],
            "sources": [],
            "notes": [],
            "experiments": [],
            "investigations": [],
            "syntheses": [],
            "follow_ups": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived_at": None,
        }
        if initial_question:
            project["questions"].append(
                {
                    "id": uuid4().hex[:8],
                    "text": initial_question,
                    "status": "open",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            projects = state.setdefault("research_projects", [])
            if len(projects) >= MAX_PROJECTS:
                raise ResearchError(
                    f"At most {MAX_PROJECTS} research projects are supported."
                )
            projects.append(deepcopy(project))
            return deepcopy(project)

        return self.store.mutate(mutation)

    def list(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        result = []
        for raw in self.store.load().get("research_projects", []):
            if not isinstance(raw, dict):
                continue
            if not include_archived and raw.get("status") == "archived":
                continue
            project = deepcopy(raw)
            project["summary"] = research_summary(project)
            result.append(project)
        return sorted(
            result,
            key=lambda item: (
                item.get("status") == "archived",
                item.get("updated_at", ""),
            ),
            reverse=True,
        )

    def show(self, project_id: str) -> dict[str, Any]:
        state = self.store.load()
        project = deepcopy(self._find(state, project_id))
        project["summary"] = research_summary(project)
        return project

    def add_question(
        self, project_id: str, text: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)
        question = {
            "id": uuid4().hex[:8],
            "text": _text(text, "question", required=True),
            "status": "open",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._append(project_id, "questions", "question", question, timestamp)

    def add_source(
        self,
        project_id: str,
        source_type: str,
        title: str,
        locator: str,
        note: str,
        *,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if source_type not in SOURCE_TYPES:
            raise ResearchError(
                f"source_type must be one of: {', '.join(SOURCE_TYPES)}."
            )
        timestamp = _timestamp(now)
        source = {
            "id": uuid4().hex[:8],
            "source_type": source_type,
            "title": _text(title, "title", required=True),
            "locator": _text(locator, "locator", limit=MAX_LOCATOR_LENGTH),
            "note": _text(note, "note"),
            "metadata": deepcopy(metadata or {}),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._append(project_id, "sources", "source", source, timestamp)

    def add_note(
        self,
        project_id: str,
        text: str,
        source_ids: list[str] | tuple[str, ...],
        tags: list[str] | tuple[str, ...],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)
        references = _unique(source_ids)
        note = {
            "id": uuid4().hex[:8],
            "text": _text(text, "note", required=True),
            "source_ids": references,
            "tags": _unique(tags, 20),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._append(
            project_id, "notes", "note", note, timestamp, source_ids=references
        )

    def add_experiment(
        self,
        project_id: str,
        title: str,
        hypothesis: str,
        method: str,
        result: str,
        status: str,
        source_ids: list[str] | tuple[str, ...],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if status not in EXPERIMENT_STATUSES:
            raise ResearchError(
                f"status must be one of: {', '.join(EXPERIMENT_STATUSES)}."
            )
        timestamp = _timestamp(now)
        references = _unique(source_ids)
        experiment = {
            "id": uuid4().hex[:8],
            "title": _text(title, "title", required=True),
            "hypothesis": _text(hypothesis, "hypothesis"),
            "method": _text(method, "method"),
            "result": _text(result, "result"),
            "status": status,
            "source_ids": references,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._append(
            project_id,
            "experiments",
            "experiment",
            experiment,
            timestamp,
            source_ids=references,
        )

    def archive(
        self, project_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            project["status"] = "archived"
            project["archived_at"] = timestamp
            project["updated_at"] = timestamp
            return deepcopy(project)

        return self.store.mutate(mutation)

    def investigate(
        self,
        project_id: str,
        query: str,
        *,
        literature_search: Any = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        clean_query = _text(query, "query", required=True, limit=500)
        timestamp = _timestamp(now)
        literature_status = "not_requested"
        rag_status = "not_requested"
        degradations: list[str] = []
        works: list[dict[str, Any]] = []
        memories: list[dict[str, Any]] = []
        if literature_search is not None:
            try:
                response = literature_search(clean_query, 5)
                raw_works = (
                    response.get("works", []) if isinstance(response, dict) else []
                )
                works = [item for item in raw_works[:5] if isinstance(item, dict)]
                literature_status = "available"
            except Exception:
                literature_status = "unavailable"
                degradations.append("literature_unavailable")
        if self.retriever is not None:
            try:
                response = self.retriever(
                    clean_query,
                    5,
                    task_context="Investigate a bounded research question.",
                    now=now,
                )
                raw_memories = (
                    response.get("results", []) if isinstance(response, dict) else []
                )
                memories = [item for item in raw_memories[:5] if isinstance(item, dict)]
                rag_status = "available"
            except Exception:
                rag_status = "unavailable"
                degradations.append("rag_unavailable")
        context = {
            "literature": literature_status,
            "rag": rag_status,
            "degradations": degradations,
        }

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            self._require_active(project)
            existing_keys = {
                self._source_key(item)
                for item in project.setdefault("sources", [])
                if isinstance(item, dict)
            }
            imported = []
            for work in works:
                key = self._work_key(work)
                if not key or key in existing_keys:
                    continue
                source = self._source_from_work(work, timestamp)
                project["sources"].append(source)
                imported.append(deepcopy(source))
                existing_keys.add(key)
            memory_refs = [
                f"memory:{str(item['id'])[:100]}" for item in memories if item.get("id")
            ]
            investigation = {
                "id": uuid4().hex[:8],
                "query": clean_query,
                "imported_source_ids": [item["id"] for item in imported],
                "memory_refs": memory_refs,
                "context": deepcopy(context),
                "created_at": timestamp,
            }
            history = project.setdefault("investigations", [])
            history.append(investigation)
            del history[:-100]
            project["updated_at"] = timestamp
            return {
                "project_id": project_id,
                "query": clean_query,
                "imported_sources": imported,
                "memory_refs": memory_refs,
                "context": deepcopy(context),
                "investigation": deepcopy(investigation),
            }

        return self.store.mutate(mutation)

    def synthesize(
        self,
        project_id: str,
        *,
        use_llm: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        project = self.show(project_id)
        self._require_active(project)
        query = self._research_query(project)
        memories, rag_status, degradations = self._retrieve(query, now)
        documents, corpus_status, corpus_degradations = self._retrieve_documents(
            project_id, query
        )
        degradations.extend(corpus_degradations)
        findings = self._evidence_findings(project, memories, documents)
        open_questions = [
            item.get("text", "")
            for item in project.get("questions", [])
            if isinstance(item, dict) and item.get("status", "open") == "open"
        ][:20]
        if not findings and project.get("objective"):
            open_questions.insert(0, project["objective"])
        completed = [
            item
            for item in project.get("experiments", [])
            if isinstance(item, dict) and item.get("status") == "completed"
        ]
        synthesis = {
            "id": uuid4().hex[:8],
            "research_question": project.get("objective") or project.get("title"),
            "current_findings": findings[:30],
            "evidence": self._evidence_catalog(project, memories, documents),
            "agreements_and_conflicts": [
                "No explicit evidence conflict has been recorded."
            ],
            "experiment_summary": [
                {
                    "experiment_id": item.get("id"),
                    "title": item.get("title"),
                    "result": item.get("result"),
                    "references": [f"experiment:{item.get('id')}"]
                    + [
                        f"source:{source_id}"
                        for source_id in item.get("source_ids", [])
                    ],
                }
                for item in completed[:20]
            ],
            "open_questions": open_questions[:20],
            "next_actions": self._next_actions(project, findings),
            "context": {
                "rag": rag_status,
                "corpus": corpus_status,
                "llm": "not_requested",
                "degradations": degradations,
            },
            "generation": "deterministic",
            "created_at": _timestamp(now),
        }
        if use_llm:
            synthesis = self._rewrite_synthesis(synthesis)

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            stored = self._find(state, project_id)
            self._require_active(stored)
            history = stored.setdefault("syntheses", [])
            history.append(deepcopy(synthesis))
            del history[:-50]
            stored["updated_at"] = synthesis["created_at"]
            return deepcopy(synthesis)

        return self.store.mutate(mutation)

    def ask(
        self,
        project_id: str,
        question: str,
        *,
        use_llm: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        clean_question = _text(question, "question", required=True, limit=1_000)
        project = self.show(project_id)
        self._require_active(project)
        memories, rag_status, degradations = self._retrieve(
            f"{self._research_query(project)} {clean_question}", now
        )
        documents, corpus_status, corpus_degradations = self._retrieve_documents(
            project_id, clean_question
        )
        degradations.extend(corpus_degradations)
        candidates = self._evidence_findings(project, memories, documents)
        query_terms = self._terms(clean_question)
        matched = [
            item
            for item in candidates
            if len(query_terms.intersection(self._terms(item["text"]))) >= 2
        ][:5]
        references = list(
            dict.fromkeys(ref for item in matched for ref in item["references"])
        )[:20]
        supported = bool(matched)
        answer = {
            "id": uuid4().hex[:8],
            "question": clean_question,
            "answer": (
                " ".join(item["text"] for item in matched)
                if supported
                else "The current research evidence is insufficient to answer this question."
            )[:4_000],
            "references": references,
            "uncertainty": "supported" if supported else "insufficient_evidence",
            "context": {
                "rag": rag_status,
                "corpus": corpus_status,
                "llm": "not_requested",
                "degradations": degradations,
            },
            "generation": "deterministic",
            "created_at": _timestamp(now),
        }
        if use_llm:
            answer = self._rewrite_answer(answer)

        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            stored = self._find(state, project_id)
            self._require_active(stored)
            history = stored.setdefault("follow_ups", [])
            history.append(deepcopy(answer))
            del history[:-100]
            stored["updated_at"] = answer["created_at"]
            return deepcopy(answer)

        return self.store.mutate(mutation)

    def _retrieve(
        self, query: str, now: datetime | None
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        if self.retriever is None:
            return [], "not_requested", []
        try:
            response = self.retriever(
                query[:4_000],
                5,
                task_context="Answer and synthesize an evidence-grounded research question.",
                now=now,
            )
            results = response.get("results", []) if isinstance(response, dict) else []
            return (
                [item for item in results[:5] if isinstance(item, dict)],
                "available",
                [],
            )
        except Exception:
            return [], "unavailable", ["rag_unavailable"]

    def _retrieve_documents(
        self, project_id: str, query: str
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        if self.corpus_search is None:
            return [], "not_requested", []
        try:
            results = self.corpus_search(project_id, query, 8)
            return (
                [item for item in results[:8] if isinstance(item, dict)],
                "available",
                [],
            )
        except Exception:
            return [], "unavailable", ["corpus_unavailable"]

    @staticmethod
    def _research_query(project: dict[str, Any]) -> str:
        parts = [str(project.get("title") or ""), str(project.get("objective") or "")]
        parts.extend(
            str(item.get("text") or "")
            for item in project.get("questions", [])[:20]
            if isinstance(item, dict)
        )
        return " ".join(parts)[:4_000]

    @staticmethod
    def _evidence_findings(
        project: dict[str, Any],
        memories: list[dict[str, Any]],
        documents: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        findings = []
        for source in project.get("sources", [])[:100]:
            if isinstance(source, dict) and source.get("note"):
                findings.append(
                    {
                        "text": str(source["note"])[:1_000],
                        "references": [f"source:{source.get('id')}"],
                    }
                )
        for note in project.get("notes", [])[:100]:
            if isinstance(note, dict) and note.get("text"):
                findings.append(
                    {
                        "text": str(note["text"])[:1_000],
                        "references": [f"note:{note.get('id')}"]
                        + [f"source:{item}" for item in note.get("source_ids", [])],
                    }
                )
        for experiment in project.get("experiments", [])[:100]:
            if isinstance(experiment, dict) and experiment.get("result"):
                findings.append(
                    {
                        "text": str(experiment["result"])[:1_000],
                        "references": [f"experiment:{experiment.get('id')}"]
                        + [
                            f"source:{item}"
                            for item in experiment.get("source_ids", [])
                        ],
                    }
                )
        for memory in memories[:5]:
            if memory.get("id") and memory.get("text"):
                findings.append(
                    {
                        "text": str(memory["text"])[:1_000],
                        "references": [f"memory:{str(memory['id'])[:100]}"],
                    }
                )
        for document in (documents or [])[:8]:
            if document.get("reference") and document.get("text"):
                findings.append(
                    {
                        "text": str(document["text"])[:1_000],
                        "references": [str(document["reference"])[:300]],
                    }
                )
        return findings

    @staticmethod
    def _evidence_catalog(
        project: dict[str, Any],
        memories: list[dict[str, Any]],
        documents: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        evidence = [
            {
                "reference": f"source:{item.get('id')}",
                "kind": "source",
                "label": str(item.get("title") or "")[:300],
            }
            for item in project.get("sources", [])[:100]
            if isinstance(item, dict) and item.get("id")
        ]
        evidence.extend(
            {
                "reference": f"memory:{str(item['id'])[:100]}",
                "kind": "memory",
                "label": "Eligible long-term memory",
            }
            for item in memories[:5]
            if item.get("id")
        )
        evidence.extend(
            {
                "reference": str(item["reference"])[:300],
                "kind": "document",
                "label": str(item.get("document", {}).get("title") or "Document chunk")[
                    :300
                ],
            }
            for item in (documents or [])[:8]
            if item.get("reference")
        )
        return evidence[:120]

    @staticmethod
    def _next_actions(
        project: dict[str, Any], findings: list[dict[str, Any]]
    ) -> list[str]:
        actions = []
        if not project.get("sources"):
            actions.append("Search for at least one relevant scholarly source.")
        if not any(
            item.get("status") == "completed" for item in project.get("experiments", [])
        ):
            actions.append("Design and complete one bounded validation experiment.")
        if not findings:
            actions.append(
                "Record an evidence-backed note before drawing a conclusion."
            )
        actions.append("Review open questions and choose the next testable question.")
        return actions[:5]

    @staticmethod
    def _terms(text: str) -> set[str]:
        stop = {
            "the",
            "a",
            "an",
            "is",
            "was",
            "what",
            "did",
            "does",
            "and",
            "or",
            "to",
            "of",
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

    @staticmethod
    def _work_key(work: dict[str, Any]) -> str:
        doi = str(work.get("doi") or "").strip().casefold()
        if doi:
            return f"doi:{doi}"
        title = str(work.get("title") or "").strip().casefold()
        return f"title:{title}" if title else ""

    @staticmethod
    def _source_key(source: dict[str, Any]) -> str:
        metadata = source.get("metadata", {})
        doi = metadata.get("doi") if isinstance(metadata, dict) else None
        if doi:
            return f"doi:{str(doi).strip().casefold()}"
        return f"title:{str(source.get('title') or '').strip().casefold()}"

    @staticmethod
    def _source_from_work(work: dict[str, Any], timestamp: str) -> dict[str, Any]:
        return {
            "id": uuid4().hex[:8],
            "source_type": "paper",
            "title": _text(work.get("title", ""), "title", required=True),
            "locator": _text(work.get("url", ""), "locator", limit=MAX_LOCATOR_LENGTH),
            "note": _text(work.get("abstract", ""), "note"),
            "metadata": {
                "doi": str(work.get("doi") or "")[:300],
                "authors": [str(item)[:200] for item in work.get("authors", [])[:20]],
                "year": work.get("year"),
                "type": str(work.get("type") or "")[:100],
                "publisher": str(work.get("publisher") or "")[:300],
            },
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _rewrite_synthesis(self, synthesis: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(synthesis)
        if self.llm is None:
            result["context"]["llm"] = "unavailable"
            result["context"]["degradations"].append("llm_unavailable")
            return result
        references = list(
            dict.fromkeys(
                reference
                for finding in result["current_findings"]
                for reference in finding["references"]
            )
        )
        envelope = {
            "finding_texts": [item["text"] for item in result["current_findings"]],
            "open_questions": result["open_questions"],
            "next_actions": result["next_actions"],
            "references": references,
        }
        try:
            payload = json.loads(
                self.llm.generate(
                    "Rewrite research narrative only. Return strict JSON with exactly finding_texts, open_questions, next_actions, and references. Preserve references exactly.",
                    json.dumps({"deterministic": envelope}, ensure_ascii=False),
                )
            )
            if not isinstance(payload, dict) or set(payload) != set(envelope):
                raise ValueError("invalid envelope")
            if payload["references"] != references:
                raise ValueError("references changed")
            for key in ("finding_texts", "open_questions", "next_actions"):
                if (
                    not isinstance(payload[key], list)
                    or len(payload[key]) != len(envelope[key])
                    or any(
                        not isinstance(item, str)
                        or not item.strip()
                        or len(item) > 4_000
                        for item in payload[key]
                    )
                ):
                    raise ValueError("narrative shape changed")
            for item, text in zip(
                result["current_findings"], payload["finding_texts"], strict=True
            ):
                item["text"] = text.strip()
            result["open_questions"] = [
                item.strip() for item in payload["open_questions"]
            ]
            result["next_actions"] = [item.strip() for item in payload["next_actions"]]
            result["generation"] = "llm_wording"
            result["context"]["llm"] = "available"
        except (ValueError, TypeError, RuntimeError, json.JSONDecodeError):
            result["context"]["llm"] = "rejected"
            result["context"]["degradations"].append("llm_rejected")
        return result

    def _rewrite_answer(self, answer: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(answer)
        if self.llm is None:
            result["context"]["llm"] = "unavailable"
            result["context"]["degradations"].append("llm_unavailable")
            return result
        envelope = {
            "answer": result["answer"],
            "references": result["references"],
            "uncertainty": result["uncertainty"],
        }
        try:
            payload = json.loads(
                self.llm.generate(
                    "Rewrite the answer only. Return strict JSON with exactly answer, references, and uncertainty. Preserve references and uncertainty exactly.",
                    json.dumps({"deterministic": envelope}, ensure_ascii=False),
                )
            )
            if not isinstance(payload, dict) or set(payload) != set(envelope):
                raise ValueError("invalid envelope")
            if (
                payload["references"] != envelope["references"]
                or payload["uncertainty"] != envelope["uncertainty"]
            ):
                raise ValueError("evidence structure changed")
            wording = payload["answer"]
            if (
                not isinstance(wording, str)
                or not wording.strip()
                or len(wording) > 4_000
            ):
                raise ValueError("answer is invalid")
            result["answer"] = wording.strip()
            result["generation"] = "llm_wording"
            result["context"]["llm"] = "available"
        except (ValueError, TypeError, RuntimeError, json.JSONDecodeError):
            result["context"]["llm"] = "rejected"
            result["context"]["degradations"].append("llm_rejected")
        return result

    @staticmethod
    def _require_active(project: dict[str, Any]) -> None:
        if project.get("status") == "archived":
            raise ResearchError("Archived research projects cannot be changed.")

    def _append(
        self,
        project_id: str,
        collection_name: str,
        result_name: str,
        item: dict[str, Any],
        timestamp: str,
        *,
        source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._find(state, project_id)
            if project.get("status") == "archived":
                raise ResearchError("Archived research projects cannot be changed.")
            if source_ids:
                existing = {
                    source.get("id")
                    for source in project.setdefault("sources", [])
                    if isinstance(source, dict)
                }
                for source_id in source_ids:
                    if source_id not in existing:
                        raise ResearchError(f"Source '{source_id}' not found.")
            collection = project.setdefault(collection_name, [])
            if len(collection) >= MAX_ITEMS:
                raise ResearchError(
                    f"At most {MAX_ITEMS} {collection_name} are supported."
                )
            collection.append(deepcopy(item))
            project["updated_at"] = timestamp
            return {"project": deepcopy(project), result_name: deepcopy(item)}

        return self.store.mutate(mutation)

    @staticmethod
    def _find(state: dict[str, Any], project_id: str) -> dict[str, Any]:
        for project in state.setdefault("research_projects", []):
            if isinstance(project, dict) and project.get("id") == project_id:
                return project
        raise ResearchError(f"Research project '{project_id}' not found.")
