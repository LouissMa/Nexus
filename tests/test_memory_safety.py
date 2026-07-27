from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nexus.memory_service import MemoryManager
from nexus.rag import MemoryRetriever
from nexus.service import NexusService
from nexus.store import JsonStore


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


def test_recent_memory_fallback_does_not_restore_forgotten_or_expired_data(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    store.save(
        {
            "memories": [
                {
                    "id": "forgotten",
                    "text": "Secret unrelated memory",
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "status": "forgotten",
                },
                {
                    "id": "expired",
                    "text": "Expired unrelated memory",
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "expires_at": "2026-07-26T00:00:00+00:00",
                },
            ],
            "goals": [],
            "daily_tasks": [],
            "rag_index": None,
        }
    )

    briefing = NexusService(store).daily_briefing(now=NOW)

    assert briefing["relevant_memories"] == []
    assert briefing["memory_retrieval"]["strategy"] == "recent_memory_fallback"


class ReindexRecorder(MemoryRetriever):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def reindex(self, memories: list[dict]) -> dict:
        self.ids = [str(memory["id"]) for memory in memories]
        return {"enabled": True, "indexed": len(memories), "error": None}


def test_manual_reindex_only_receives_currently_eligible_memories(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path / "state.json")
    store.save(
        {
            "memories": [
                {
                    "id": "active",
                    "text": "Current fact",
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "id": "archived",
                    "text": "Old fact",
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "status": "archived",
                },
                {
                    "id": "forgotten",
                    "text": "Forgotten fact",
                    "tags": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "status": "forgotten",
                },
            ],
            "goals": [],
            "daily_tasks": [],
            "rag_index": None,
        }
    )
    recorder = ReindexRecorder()

    MemoryManager(store, recorder).reindex()

    assert recorder.ids == ["active"]
