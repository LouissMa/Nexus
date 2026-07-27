from __future__ import annotations

from dataclasses import dataclass
import inspect

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .memory_lifecycle import (
    PRIVACY_SCOPES,
    MemoryLifecycleError,
    apply_transition,
    build_compression_plan,
    detect_duplicate,
    is_memory_eligible,
    normalize_memory,
    parse_memory_time,
    utc_iso,
    validate_importance,
)
from .rag import MemoryRetriever
from .store import JsonStore

UNSET = object()


@dataclass
class ManagedMemory:
    id: str
    text: str
    tags: list[str]
    created_at: str
    updated_at: str
    importance: float
    importance_source: str
    pinned: bool
    privacy: str
    status: str
    expires_at: str | None
    duplicate_of: str | None
    duplicate_kind: str | None = None
    duplicate_similarity: float = 0.0
    index_sync: dict[str, Any] | None = None


class MemoryManager:
    """Owns persistent memory lifecycle operations for NexusService."""

    def __init__(self, store: JsonStore, retriever: MemoryRetriever):
        self.store = store
        self.retriever = retriever

    def add(
        self,
        text: str,
        tags: list[str],
        *,
        importance: float | None = None,
        privacy: str = "private",
        expires_at: str | None = None,
        pinned: bool = False,
        now: datetime | None = None,
    ) -> ManagedMemory:
        current = self._aware(now)
        state = self.store.load()
        duplicate = detect_duplicate(state.get("memories", []), text, tags)
        if duplicate.kind == "exact" and duplicate.memory_id:
            existing = self._find(state, duplicate.memory_id)
            existing["duplicate_count"] = int(existing.get("duplicate_count", 0)) + 1
            existing["last_seen_at"] = utc_iso(current)
            existing["updated_at"] = utc_iso(current)
            self.store.save(state)
            return self._managed(
                normalize_memory(existing, now=current),
                duplicate_kind="exact",
                duplicate_similarity=1.0,
                index_sync=None,
            )

        timestamp = utc_iso(current)
        record: dict[str, Any] = {
            "id": str(uuid4())[:8],
            "text": text.strip(),
            "tags": tags,
            "created_at": timestamp,
            "updated_at": timestamp,
            "pinned": pinned,
            "privacy": privacy,
            "expires_at": expires_at,
            "duplicate_of": duplicate.memory_id if duplicate.kind == "near" else None,
        }
        if importance is not None:
            record["importance"] = importance
            record["importance_source"] = "user"
        normalized = normalize_memory(record, now=current)
        enriched = self.retriever.enrich_memory(normalized)
        state["memories"].append(enriched)
        report = self.retriever.index_memories([enriched])
        self._record_index_report(state, report, current)
        self.store.save(state)
        return self._managed(
            enriched,
            duplicate_kind=duplicate.kind if duplicate.kind == "near" else None,
            duplicate_similarity=duplicate.similarity,
            index_sync=self._index_sync(report),
        )

    def list(
        self,
        *,
        include_archived: bool = False,
        include_forgotten: bool = False,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        memories: list[dict[str, Any]] = []
        for raw in self.store.load().get("memories", []):
            item = normalize_memory(raw, now=now)
            if item["status"] == "forgotten":
                if include_forgotten:
                    memories.append(item)
                continue
            if not is_memory_eligible(
                item,
                privacy="private",
                include_archived=include_archived,
                now=now,
            ):
                continue
            memories.append(item)
        memories.sort(key=lambda item: item["created_at"], reverse=True)
        return [self._public(item) for item in memories]

    def show(self, memory_id: str) -> dict[str, Any]:
        state = self.store.load()
        return self._public(normalize_memory(self._find(state, memory_id)))

    def search(
        self,
        query: str,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        terms = {part.lower() for part in query.split() if part.strip()}
        results: list[tuple[int, dict[str, Any]]] = []
        for memory in self.list(now=now):
            haystack = f"{memory['text']} {' '.join(memory.get('tags', []))}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                results.append((score, memory))
        results.sort(key=lambda item: (-item[0], item[1]["created_at"]))
        return [memory for _, memory in results]

    def retrieve(
        self,
        query: str,
        limit: int,
        *,
        privacy: str = "private",
        include_archived: bool = False,
        task_context: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        state = self.store.load()
        parameters = inspect.signature(self.retriever.retrieve_result).parameters
        if "privacy" in parameters:
            result = self.retriever.retrieve_result(
                state.get("memories", []),
                query,
                limit,
                privacy=privacy,
                include_archived=include_archived,
                task_context=task_context or query,
                now=now,
            )
        else:
            result = self.retriever.retrieve_result(
                state.get("memories", []), query, limit
            )
        return {
            "query": query,
            "results": result.memories,
            "memory_retrieval": result.metadata,
        }

    def update(
        self,
        memory_id: str,
        *,
        importance: float | None = None,
        privacy: str | None = None,
        expires_at: str | None | object = UNSET,
        pinned: bool | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._aware(now)
        state = self.store.load()
        memory = self._find(state, memory_id)
        if memory.get("summary_of") and (
            privacy is not None or expires_at is not UNSET or pinned is not None
        ):
            raise MemoryLifecycleError(
                "Derived summary privacy, expiry, and pinning are controlled by its sources."
            )
        if importance is not None:
            memory["importance"] = validate_importance(importance)
            memory["importance_source"] = "user"
        if privacy is not None:
            if privacy not in PRIVACY_SCOPES:
                raise MemoryLifecycleError(
                    f"privacy must be one of: {', '.join(PRIVACY_SCOPES)}."
                )
            memory["privacy"] = privacy
        if expires_at is not UNSET:
            memory["expires_at"] = expires_at
        if pinned is not None:
            memory["pinned"] = pinned
        memory["updated_at"] = utc_iso(current)
        self._replace(memory, normalize_memory(memory, now=current))
        self._refresh_derived_summary_policies(state, memory_id, current)
        report = self._save_mutation(state, current)
        return self._with_index_sync(self._public(memory), report)

    def relate(
        self,
        memory_id: str,
        relation: str,
        target_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if memory_id == target_id:
            raise MemoryLifecycleError("A memory cannot relate to itself.")
        current = self._aware(now)
        state = self.store.load()
        memory = self._find(state, memory_id)
        target = self._find(state, target_id)
        if relation == "supersedes":
            if target.get("status", "active") == "forgotten":
                raise MemoryLifecycleError("A forgotten memory cannot be superseded.")
            memory["supersedes"] = target_id
            self._replace(target, apply_transition(target, "archive", now=current))
        elif relation == "conflicts_with":
            memory["conflicts_with"] = list(
                dict.fromkeys([*memory.get("conflicts_with", []), target_id])
            )
            target["conflicts_with"] = list(
                dict.fromkeys([*target.get("conflicts_with", []), memory_id])
            )
        else:
            raise MemoryLifecycleError(
                "relation must be one of: supersedes, conflicts_with."
            )
        memory["updated_at"] = utc_iso(current)
        target["updated_at"] = utc_iso(current)
        report = self._save_mutation(state, current)
        return {
            "relation": relation,
            "index_sync": self._index_sync(report),
            "memory": self._public(normalize_memory(memory, now=current)),
            "target": self._public(normalize_memory(target, now=current)),
        }

    def transition(
        self,
        memory_id: str,
        transition: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._aware(now)
        state = self.store.load()
        memory = self._find(state, memory_id)
        if transition == "restore":
            self._validate_summary_restore(state, memory, current)
        self._replace(memory, apply_transition(memory, transition, now=current))
        if transition == "forget":
            self._cascade_forget_summaries(state, memory_id, current)
        report = self._save_mutation(state, current)
        return self._with_index_sync(self._public(memory), report)

    def purge(self, memory_id: str, *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise MemoryLifecycleError(
                "Permanent purge requires explicit confirmation."
            )
        state = self.store.load()
        memory = self._find(state, memory_id)
        if memory.get("status", "active") != "forgotten":
            raise MemoryLifecycleError(
                "Only a forgotten memory can be permanently purged."
            )
        current = datetime.now(UTC)
        self._purge_derived_summaries(state, memory_id)
        state["memories"] = [
            item for item in state.get("memories", []) if item.get("id") != memory_id
        ]
        report = self._save_mutation(state, current)
        return {
            "purged": True,
            "memory_id": memory_id,
            "index_sync": self._index_sync(report),
        }

    def compress(
        self,
        *,
        older_than_days: int,
        max_importance: float,
        dry_run: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._aware(now)
        state = self.store.load()
        plans = build_compression_plan(
            state.get("memories", []),
            older_than_days=older_than_days,
            max_importance=max_importance,
            now=current,
        )
        groups = [
            {
                "group_key": plan.group_key,
                "source_ids": plan.source_ids,
                "summary_text": plan.summary_text,
                "tags": plan.tags,
                "privacy": plan.privacy,
                "expires_at": plan.expires_at,
            }
            for plan in plans
        ]
        if dry_run:
            return {"dry_run": True, "groups": groups, "created": [], "archived": []}

        created: list[str] = []
        archived: list[str] = []
        by_id = {str(item.get("id")): item for item in state.get("memories", [])}
        for plan in plans:
            summary_id = str(uuid4())[:8]
            summary = normalize_memory(
                {
                    "id": summary_id,
                    "text": plan.summary_text,
                    "tags": plan.tags,
                    "created_at": utc_iso(current),
                    "updated_at": utc_iso(current),
                    "importance": min(0.6, max_importance + 0.1),
                    "importance_source": "automatic",
                    "privacy": plan.privacy,
                    "expires_at": plan.expires_at,
                    "summary_of": plan.source_ids,
                },
                now=current,
            )
            state["memories"].append(self.retriever.enrich_memory(summary))
            created.append(summary_id)
            for source_id in plan.source_ids:
                source = by_id[source_id]
                self._replace(source, apply_transition(source, "archive", now=current))
                archived.append(source_id)
        report = self._save_mutation(state, current) if plans else None
        return {
            "dry_run": False,
            "index_sync": self._index_sync(report),
            "groups": groups,
            "created": created,
            "archived": archived,
        }

    def maintain(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool,
    ) -> dict[str, Any]:
        current = self._aware(now)
        state = self.store.load()
        expired_ids: list[str] = []
        for memory in state.get("memories", []):
            item = normalize_memory(memory, now=current)
            expires_at = parse_memory_time(item.get("expires_at"), "expires_at")
            if (
                item["status"] == "active"
                and not item["pinned"]
                and expires_at is not None
                and expires_at <= current
            ):
                expired_ids.append(str(item["id"]))
        if dry_run:
            return {
                "dry_run": True,
                "expired_ids": expired_ids,
                "archived_ids": [],
            }
        for memory_id in expired_ids:
            memory = self._find(state, memory_id)
            self._replace(memory, apply_transition(memory, "archive", now=current))
        report = self._save_mutation(state, current) if expired_ids else None
        return {
            "dry_run": False,
            "index_sync": self._index_sync(report),
            "expired_ids": expired_ids,
            "archived_ids": expired_ids,
        }

    def reindex(self) -> dict[str, Any]:
        state = self.store.load()
        active = [
            item
            for item in state.get("memories", [])
            if is_memory_eligible(item, privacy="private")
        ]
        report = self.retriever.reindex(active)
        self._record_index_report(state, report, datetime.now(UTC))
        self.store.save(state)
        return report

    def status(self) -> dict[str, Any]:
        state = self.store.load()
        counts = {"active": 0, "archived": 0, "forgotten": 0}
        for memory in state.get("memories", []):
            status = normalize_memory(memory)["status"]
            counts[status] += 1
        return {
            "runtime": self.retriever.status(),
            "last_index": state.get("rag_index"),
            "memory_count": len(state.get("memories", [])),
            "lifecycle_counts": counts,
        }

    def _save_mutation(
        self, state: dict[str, Any], now: datetime
    ) -> dict[str, Any] | None:
        active = [
            item
            for item in state.get("memories", [])
            if is_memory_eligible(item, privacy="private", now=now)
        ]
        report = self.retriever.index_memories(active, recreate=True)
        self._record_index_report(state, report, now)
        self.store.save(state)
        return report

    @staticmethod
    def _index_sync(report: dict[str, Any] | None) -> dict[str, Any] | None:
        if report is None:
            return None
        return {
            key: report.get(key)
            for key in (
                "enabled",
                "provider",
                "model",
                "indexed",
                "updated_at",
                "error",
            )
            if key in report
        }

    @classmethod
    def _with_index_sync(
        cls,
        result: dict[str, Any],
        report: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result["index_sync"] = cls._index_sync(report)
        return result

    @staticmethod
    def _cascade_forget_summaries(
        state: dict[str, Any],
        source_id: str,
        now: datetime,
    ) -> None:
        pending = [source_id]
        visited: set[str] = set()
        while pending:
            current_id = pending.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            for memory in state.get("memories", []):
                if current_id not in memory.get("summary_of", []):
                    continue
                if memory.get("status", "active") == "forgotten":
                    continue
                memory_id = str(memory["id"])
                MemoryManager._replace(
                    memory,
                    apply_transition(memory, "forget", now=now),
                )
                pending.append(memory_id)

    @staticmethod
    def _validate_summary_restore(
        state: dict[str, Any], memory: dict[str, Any], now: datetime
    ) -> None:
        source_ids = memory.get("summary_of", [])
        if not source_ids:
            return
        by_id = {str(item.get("id")): item for item in state.get("memories", [])}
        for source_id in source_ids:
            source = by_id.get(str(source_id))
            if source is None or source.get("status", "active") == "forgotten":
                raise MemoryLifecycleError(
                    "A derived summary cannot be restored while a source is forgotten or purged."
                )
        MemoryManager._apply_derived_policy(
            memory,
            [by_id[str(source_id)] for source_id in source_ids],
            now,
        )

    @staticmethod
    def _purge_derived_summaries(state: dict[str, Any], source_id: str) -> None:
        pending = [source_id]
        derived_ids: set[str] = set()
        while pending:
            current_id = pending.pop()
            for memory in state.get("memories", []):
                memory_id = str(memory.get("id"))
                if memory_id in derived_ids:
                    continue
                if current_id not in memory.get("summary_of", []):
                    continue
                derived_ids.add(memory_id)
                pending.append(memory_id)
        if derived_ids:
            state["memories"] = [
                memory
                for memory in state.get("memories", [])
                if str(memory.get("id")) not in derived_ids
            ]

    @staticmethod
    def _refresh_derived_summary_policies(
        state: dict[str, Any], source_id: str, now: datetime
    ) -> None:
        by_id = {str(item.get("id")): item for item in state.get("memories", [])}
        pending = [source_id]
        visited: set[str] = set()
        while pending:
            current_id = pending.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            for summary in state.get("memories", []):
                if current_id not in summary.get("summary_of", []):
                    continue
                sources = [by_id.get(str(item)) for item in summary["summary_of"]]
                if any(
                    source is None or source.get("status", "active") == "forgotten"
                    for source in sources
                ):
                    if summary.get("status", "active") != "forgotten":
                        MemoryManager._replace(
                            summary,
                            apply_transition(summary, "forget", now=now),
                        )
                else:
                    MemoryManager._apply_derived_policy(
                        summary,
                        [source for source in sources if source is not None],
                        now,
                    )
                pending.append(str(summary["id"]))

    @staticmethod
    def _apply_derived_policy(
        summary: dict[str, Any],
        sources: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        summary["privacy"] = min(
            (str(source.get("privacy", "private")) for source in sources),
            key=PRIVACY_SCOPES.index,
        )
        expiries = [
            parse_memory_time(source.get("expires_at"), "expires_at")
            for source in sources
            if source.get("expires_at")
        ]
        earliest = min(expiries) if expiries else None
        summary["expires_at"] = utc_iso(earliest) if earliest else None
        summary["pinned"] = False
        summary["updated_at"] = utc_iso(now)

    def _record_index_report(
        self,
        state: dict[str, Any],
        report: dict[str, Any] | None,
        now: datetime,
    ) -> None:
        if report is None:
            return
        report["updated_at"] = utc_iso(now)
        report["memory_count"] = len(state.get("memories", []))
        state["rag_index"] = report

    @staticmethod
    def _find(state: dict[str, Any], memory_id: str) -> dict[str, Any]:
        for memory in state.get("memories", []):
            if memory.get("id") == memory_id:
                return memory
        raise MemoryLifecycleError(f"Memory '{memory_id}' not found.")

    @staticmethod
    def _replace(target: dict[str, Any], replacement: dict[str, Any]) -> None:
        target.clear()
        target.update(replacement)

    @staticmethod
    def _public(memory: dict[str, Any]) -> dict[str, Any]:
        public = dict(memory)
        public.pop("embedding", None)
        return public

    @staticmethod
    def _managed(
        memory: dict[str, Any],
        *,
        duplicate_kind: str | None,
        duplicate_similarity: float,
        index_sync: dict[str, Any] | None,
    ) -> ManagedMemory:
        item = normalize_memory(memory)
        return ManagedMemory(
            id=str(item["id"]),
            text=str(item["text"]),
            tags=list(item["tags"]),
            created_at=str(item["created_at"]),
            updated_at=str(item["updated_at"]),
            importance=float(item["importance"]),
            importance_source=str(item["importance_source"]),
            pinned=bool(item["pinned"]),
            privacy=str(item["privacy"]),
            status=str(item["status"]),
            expires_at=item.get("expires_at"),
            duplicate_of=item.get("duplicate_of"),
            duplicate_kind=duplicate_kind,
            duplicate_similarity=duplicate_similarity,
            index_sync=index_sync,
        )

    @staticmethod
    def _aware(value: datetime | None) -> datetime:
        result = value or datetime.now(UTC)
        if result.tzinfo is None:
            result = result.replace(tzinfo=UTC)
        return result.astimezone(UTC)
