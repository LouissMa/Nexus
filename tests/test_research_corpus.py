from __future__ import annotations

from pathlib import Path

import pytest

from nexus.research import ResearchService
from nexus.research_corpus import CorpusError, ResearchCorpus
from nexus.store import JsonStore


def corpus(tmp_path: Path, pdf_reader=None) -> tuple[ResearchCorpus, str]:
    store = JsonStore(tmp_path / "home" / "state.json")
    project = ResearchService(store).create("Corpus", "Ground every claim.")
    return ResearchCorpus(store, pdf_reader=pdf_reader), project["id"]


def test_ingest_text_search_validate_and_remove(tmp_path: Path) -> None:
    service, project_id = corpus(tmp_path)
    path = tmp_path / "evidence.md"
    path.write_text(
        "# Retrieval\n\nHybrid retrieval improves recall.\n\n"
        "The evaluation used twenty queries.",
        encoding="utf-8",
    )

    added = service.ingest_file(project_id, path)
    duplicate = service.ingest_file(project_id, path)
    results = service.search(project_id, "hybrid retrieval recall", limit=3)

    assert added["document"]["kind"] == "markdown"
    assert added["document"]["chunk_count"] >= 1
    assert duplicate["status"] == "unchanged"
    assert results[0]["reference"].startswith(
        f"document:{added['document']['id']}#lines="
    )
    assert service.validate_reference(results[0]["reference"])["valid"] is True
    assert service.remove_document(project_id, added["document"]["id"])["removed"]
    assert service.validate_reference(results[0]["reference"])["valid"] is False


def test_pdf_chunks_preserve_page_numbers(tmp_path: Path) -> None:
    service, project_id = corpus(
        tmp_path,
        pdf_reader=lambda _path: [
            (1, "Introduction to grounded research."),
            (2, "The second page reports improved precision."),
        ],
    )
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-test")

    added = service.ingest_file(project_id, path)
    result = service.search(project_id, "improved precision", limit=1)[0]

    assert added["document"]["kind"] == "pdf"
    assert "#page=2&chunk=" in result["reference"]
    assert service.validate_reference(result["reference"])["valid"] is True


def test_reindex_is_atomic_and_rejects_invalid_files(tmp_path: Path) -> None:
    service, project_id = corpus(tmp_path)
    path = tmp_path / "notes.txt"
    path.write_text("Original evidence remains searchable.", encoding="utf-8")
    document = service.ingest_file(project_id, path)["document"]
    original = service.search(project_id, "original evidence", limit=1)
    path.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(CorpusError, match="text"):
        service.reindex_document(project_id, document["id"])

    assert service.search(project_id, "original evidence", limit=1) == original

    unsupported = tmp_path / "image.png"
    unsupported.write_bytes(b"png")
    with pytest.raises(CorpusError, match="Supported"):
        service.ingest_file(project_id, unsupported)


def test_reference_detects_tampered_chunk(tmp_path: Path) -> None:
    service, project_id = corpus(tmp_path)
    path = tmp_path / "evidence.txt"
    path.write_text("Citation integrity matters.", encoding="utf-8")
    service.ingest_file(project_id, path)
    result = service.search(project_id, "citation integrity", limit=1)[0]
    index_path = next((tmp_path / "home" / "research_corpus").rglob("*.json"))
    payload = index_path.read_text(encoding="utf-8").replace(
        "Citation integrity matters.", "Tampered text"
    )
    index_path.write_text(payload, encoding="utf-8")

    validation = service.validate_reference(result["reference"])

    assert validation == {"valid": False, "reason": "content_hash_mismatch"}
