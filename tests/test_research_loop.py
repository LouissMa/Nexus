from __future__ import annotations

from pathlib import Path

from nexus.research import ResearchService
from nexus.research_corpus import ResearchCorpus
from nexus.research_loop import ResearchLoop
from nexus.store import JsonStore


def setup(tmp_path: Path) -> tuple[ResearchLoop, ResearchService, ResearchCorpus, str]:
    store = JsonStore(tmp_path / "home" / "state.json")
    research = ResearchService(store)
    project = research.create(
        "Loop", "Evaluate retrieval.", "Does hybrid retrieval improve recall?"
    )
    corpus = ResearchCorpus(store)
    return ResearchLoop(store, research, corpus), research, corpus, project["id"]


def test_research_loop_terminates_with_verified_evidence(tmp_path: Path) -> None:
    loop, research, corpus, project_id = setup(tmp_path)
    path = tmp_path / "paper.md"
    path.write_text(
        "Hybrid retrieval improved recall by twelve percent in the evaluation.",
        encoding="utf-8",
    )
    corpus.ingest_file(project_id, path)

    result = loop.run(project_id, "Does hybrid retrieval improve recall?", max_cycles=3)

    assert result["terminal_reason"] == "complete"
    assert result["cycles"] == 1
    assert result["findings"][0]["references"]
    assert all(
        corpus.validate_reference(ref)["valid"]
        for ref in result["findings"][0]["references"]
    )
    assert [step["agent"] for step in result["trace"]] == [
        "planner",
        "retriever",
        "analyst",
        "critic",
        "reflection",
    ]
    assert research.show(project_id)["research_runs"][0]["id"] == result["id"]


def test_research_loop_reports_insufficient_evidence(tmp_path: Path) -> None:
    loop, _research, _corpus, project_id = setup(tmp_path)

    result = loop.run(project_id, "What is the energy cost?", max_cycles=2)

    assert result["terminal_reason"] == "needs_evidence"
    assert result["findings"] == []
    assert result["open_questions"] == ["What is the energy cost?"]


def test_research_loop_rejects_valid_but_irrelevant_document(tmp_path: Path) -> None:
    loop, _research, corpus, project_id = setup(tmp_path)
    path = tmp_path / "unrelated.md"
    path.write_text(
        "The retrieval study measured recall on twenty benchmark queries.",
        encoding="utf-8",
    )
    corpus.ingest_file(project_id, path)

    result = loop.run(project_id, "What is the GPU energy cost?", max_cycles=2)

    assert result["terminal_reason"] == "needs_evidence"
    assert result["findings"] == []
    assert result["trace"][3]["metadata"]["rejected"] >= 1


def test_research_loop_degrades_when_retrieval_fails(tmp_path: Path) -> None:
    loop, _research, corpus, project_id = setup(tmp_path)

    def broken(*_args, **_kwargs):
        raise RuntimeError("index unavailable")

    corpus.search = broken  # type: ignore[method-assign]
    result = loop.run(project_id, "Does it work?", max_cycles=1)

    assert result["terminal_reason"] == "needs_evidence"
    assert result["degradations"] == ["corpus_unavailable"]
    assert result["trace"][1]["status"] == "degraded"
