from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.research import ResearchService
from nexus.store import JsonStore


NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


def service(tmp_path: Path) -> ResearchService:
    return ResearchService(JsonStore(tmp_path / "state.json"))


def test_create_and_list_research_projects(tmp_path: Path) -> None:
    research = service(tmp_path)

    project = research.create(
        "RAG evaluation",
        "Evaluate retrieval quality for personal long-term memory.",
        "Which metrics reflect useful personal memory retrieval?",
        now=NOW,
    )

    assert project["status"] == "active"
    assert project["questions"][0]["text"].startswith("Which metrics")
    assert project["sources"] == []
    assert research.show(project["id"])["id"] == project["id"]
    assert research.list()[0]["summary"]["question_count"] == 1


def test_add_research_evidence_and_validate_references(tmp_path: Path) -> None:
    research = service(tmp_path)
    project = research.create(
        "Hybrid RAG", "Compare retrieval strategies.", "", now=NOW
    )
    question = research.add_question(
        project["id"], "Does fusion improve recall?", now=NOW
    )
    source = research.add_source(
        project["id"],
        "paper",
        "Hybrid retrieval evaluation",
        "https://doi.org/10.1000/example",
        "Reports stronger recall for fused retrieval.",
        now=NOW,
    )
    note = research.add_note(
        project["id"],
        "The reported gain may depend on the benchmark.",
        [source["source"]["id"]],
        ["retrieval", "evaluation"],
        now=NOW,
    )
    experiment = research.add_experiment(
        project["id"],
        "Dense versus hybrid",
        "Hybrid retrieval improves recall.",
        "Run the same 20 queries through both retrievers.",
        "Hybrid recovered two additional relevant memories.",
        "completed",
        [source["source"]["id"]],
        now=NOW,
    )

    shown = research.show(project["id"])
    assert question["question"]["status"] == "open"
    assert note["note"]["source_ids"] == [source["source"]["id"]]
    assert experiment["experiment"]["status"] == "completed"
    assert shown["summary"] == {
        "question_count": 1,
        "source_count": 1,
        "note_count": 1,
        "experiment_count": 1,
        "investigation_count": 0,
        "synthesis_count": 0,
        "follow_up_count": 0,
        "document_count": 0,
        "research_run_count": 0,
    }
    with pytest.raises(ValueError, match="Source 'missing' not found"):
        research.add_note(project["id"], "Unsupported", ["missing"], [], now=NOW)


def test_research_validation_and_archival(tmp_path: Path) -> None:
    research = service(tmp_path)
    with pytest.raises(ValueError, match="title is required"):
        research.create("", "", "", now=NOW)
    project = research.create("Research", "", "", now=NOW)
    with pytest.raises(ValueError, match="source_type"):
        research.add_source(project["id"], "video", "A", "", "", now=NOW)
    with pytest.raises(ValueError, match="status"):
        research.add_experiment(project["id"], "Trial", "", "", "", "done", [], now=NOW)
    with pytest.raises(ValueError, match="at most"):
        research.add_note(project["id"], "x" * 4_001, [], [], now=NOW)

    archived = research.archive(project["id"], now=NOW)

    assert archived["status"] == "archived"
    assert research.list() == []
    assert research.list(include_archived=True)[0]["id"] == project["id"]


def test_legacy_state_normalizes_research_collection(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "state.json")
    state = store.load()
    state.pop("research_projects")
    store.save(state)

    assert store.load()["research_projects"] == []


def test_investigate_combines_literature_and_rag_with_deduplication(
    tmp_path: Path,
) -> None:
    retrieval_calls: list[str] = []

    def retrieve(query: str, limit: int, **_: object) -> dict[str, object]:
        retrieval_calls.append(query)
        return {
            "results": [
                {
                    "id": "memory-1",
                    "text": "Previous tests favored hybrid retrieval.",
                    "retrieval_score": 0.91,
                }
            ],
            "metadata": {"strategy": "hybrid"},
        }

    def search(query: str, limit: int) -> dict[str, object]:
        assert query == "hybrid retrieval evaluation"
        assert limit == 5
        work = {
            "doi": "10.1000/example",
            "title": "Hybrid retrieval evaluation",
            "authors": ["Ada Lovelace"],
            "year": 2026,
            "type": "journal-article",
            "publisher": "Example Press",
            "abstract": "Hybrid fusion improved recall on the benchmark.",
            "url": "https://doi.org/10.1000/example",
        }
        return {"works": [work, dict(work)], "count": 2}

    research = ResearchService(JsonStore(tmp_path / "state.json"), retriever=retrieve)
    project = research.create("RAG", "Evaluate hybrid retrieval.", "", now=NOW)

    result = research.investigate(
        project["id"],
        "hybrid retrieval evaluation",
        literature_search=search,
        now=NOW,
    )

    assert retrieval_calls
    assert result["context"] == {
        "literature": "available",
        "rag": "available",
        "degradations": [],
    }
    assert len(result["imported_sources"]) == 1
    assert result["memory_refs"] == ["memory:memory-1"]
    assert research.show(project["id"])["summary"]["investigation_count"] == 1


def test_investigate_degrades_dependencies_independently(tmp_path: Path) -> None:
    def broken_retriever(*_: object, **__: object) -> object:
        raise RuntimeError("vector database unavailable")

    def broken_search(*_: object, **__: object) -> object:
        raise RuntimeError("network unavailable")

    research = ResearchService(
        JsonStore(tmp_path / "state.json"), retriever=broken_retriever
    )
    project = research.create("Offline", "Keep local research useful.", "", now=NOW)

    result = research.investigate(
        project["id"], "offline research", literature_search=broken_search, now=NOW
    )

    assert result["context"] == {
        "literature": "unavailable",
        "rag": "unavailable",
        "degradations": ["literature_unavailable", "rag_unavailable"],
    }
    assert result["imported_sources"] == []


def test_synthesize_and_ask_return_evidence_references(tmp_path: Path) -> None:
    def retrieve(*_: object, **__: object) -> dict[str, object]:
        return {
            "results": [
                {
                    "id": "memory-1",
                    "text": "Sparse fallback preserved offline retrieval.",
                    "retrieval_score": 0.8,
                }
            ],
            "metadata": {"strategy": "hybrid"},
        }

    research = ResearchService(JsonStore(tmp_path / "state.json"), retriever=retrieve)
    project = research.create(
        "RAG evaluation",
        "Compare dense and hybrid retrieval.",
        "What improves recall?",
        now=NOW,
    )
    source = research.add_source(
        project["id"],
        "paper",
        "Hybrid retrieval study",
        "https://doi.org/10.1000/example",
        "Hybrid fusion improved recall on the benchmark.",
        now=NOW,
    )["source"]
    research.add_note(
        project["id"],
        "The benchmark gain was two relevant memories.",
        [source["id"]],
        ["evaluation"],
        now=NOW,
    )
    research.add_experiment(
        project["id"],
        "Local comparison",
        "Hybrid improves recall.",
        "Compare twenty queries.",
        "Hybrid recovered two more relevant memories.",
        "completed",
        [source["id"]],
        now=NOW,
    )

    synthesis = research.synthesize(project["id"], now=NOW)
    answer = research.ask(
        project["id"], "Did hybrid retrieval improve recall?", now=NOW
    )
    unknown = research.ask(project["id"], "What is the GPU energy cost?", now=NOW)

    refs = {
        ref
        for finding in synthesis["current_findings"]
        for ref in finding["references"]
    }
    assert f"source:{source['id']}" in refs
    assert "memory:memory-1" in refs
    assert synthesis["open_questions"]
    assert synthesis["next_actions"]
    assert answer["uncertainty"] == "supported"
    assert answer["references"]
    assert unknown["uncertainty"] == "insufficient_evidence"


def test_chinese_question_matches_chinese_research_evidence(tmp_path: Path) -> None:
    research = service(tmp_path)
    project = research.create(
        "混合检索研究",
        "验证混合检索是否提升召回率",
        "",
        now=NOW,
    )
    source = research.add_source(
        project["id"],
        "paper",
        "混合检索评估",
        "https://doi.org/10.1000/chinese-example",
        "实验结果显示混合检索提升了召回率。",
        now=NOW,
    )["source"]

    answer = research.ask(project["id"], "混合检索是否提升召回率？", now=NOW)

    assert answer["uncertainty"] == "supported"
    assert answer["references"] == [f"source:{source['id']}"]


class StaticLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "references" in system_prompt
        assert "deterministic" in user_prompt
        return self.response


def test_llm_can_rewrite_answer_without_changing_evidence(tmp_path: Path) -> None:
    import json

    llm = StaticLLM(
        json.dumps(
            {
                "answer": "The available evidence supports a recall improvement.",
                "references": ["memory:memory-1"],
                "uncertainty": "supported",
            }
        )
    )

    def retrieve(*_: object, **__: object) -> dict[str, object]:
        return {
            "results": [
                {
                    "id": "memory-1",
                    "text": "Hybrid retrieval improved recall in the evaluation.",
                }
            ]
        }

    research = ResearchService(
        JsonStore(tmp_path / "state.json"), retriever=retrieve, llm=llm
    )
    project = research.create("RAG", "Evaluate hybrid retrieval.", "", now=NOW)

    answer = research.ask(
        project["id"], "Did hybrid retrieval improve recall?", use_llm=True, now=NOW
    )

    assert answer["generation"] == "llm_wording"
    assert answer["answer"].startswith("The available evidence")
    assert answer["references"] == ["memory:memory-1"]
    assert answer["context"]["llm"] == "available"


def test_llm_reference_change_is_rejected(tmp_path: Path) -> None:
    import json

    llm = StaticLLM(
        json.dumps(
            {
                "answer": "Unsupported answer.",
                "references": ["source:invented"],
                "uncertainty": "supported",
            }
        )
    )

    def retrieve(*_: object, **__: object) -> dict[str, object]:
        return {
            "results": [{"id": "memory-1", "text": "Hybrid retrieval improved recall."}]
        }

    research = ResearchService(
        JsonStore(tmp_path / "state.json"), retriever=retrieve, llm=llm
    )
    project = research.create("RAG", "Evaluate hybrid retrieval.", "", now=NOW)

    answer = research.ask(
        project["id"], "Did hybrid retrieval improve recall?", use_llm=True, now=NOW
    )

    assert answer["generation"] == "deterministic"
    assert answer["references"] == ["memory:memory-1"]
    assert answer["context"]["llm"] == "rejected"
    assert "llm_rejected" in answer["context"]["degradations"]
