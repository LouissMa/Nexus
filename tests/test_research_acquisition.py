from __future__ import annotations

from pathlib import Path

import pytest

from nexus.research import ResearchService
from nexus.research_corpus import CorpusError, ResearchCorpus
from nexus.store import JsonStore


def setup(tmp_path: Path, *, resolver=None) -> tuple[ResearchCorpus, str]:
    store = JsonStore(tmp_path / "home" / "state.json")
    project = ResearchService(store).create("Acquisition", "Collect evidence.")
    return ResearchCorpus(store, resolver=resolver), project["id"]


def test_ingest_https_page_extracts_title_and_text(tmp_path: Path) -> None:
    service, project_id = setup(tmp_path, resolver=lambda _host: ["93.184.216.34"])

    def fetcher(url: str, _limit: int) -> dict[str, object]:
        assert url == "https://example.com/paper"
        return {
            "url": url,
            "content_type": "text/html; charset=utf-8",
            "body": b"<html><head><title>Study</title><script>x</script></head>"
            b"<body><h1>Finding</h1><p>Grounded agents reduce errors.</p></body></html>",
        }

    result = service.ingest_web(
        project_id, "https://example.com/paper", fetcher=fetcher
    )
    hit = service.search(project_id, "grounded agents errors", limit=1)[0]

    assert result["document"]["title"] == "Study"
    assert result["document"]["kind"] == "web"
    assert "script" not in hit["text"].lower()
    assert "#lines=" in hit["reference"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://localhost/resource",
        "https://example.com:8443/resource",
    ],
)
def test_web_policy_rejects_unsafe_urls(tmp_path: Path, url: str) -> None:
    service, project_id = setup(tmp_path, resolver=lambda _host: ["127.0.0.1"])

    with pytest.raises(CorpusError):
        service.ingest_web(project_id, url, fetcher=lambda *_args: {})


def test_repository_index_is_bounded_and_line_aware(tmp_path: Path) -> None:
    service, project_id = setup(tmp_path)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "src" / "retrieval.py").write_text(
        "def fuse():\n    return 'hybrid recall'\n", encoding="utf-8"
    )
    (repo / ".git" / "secret.txt").write_text("ignored", encoding="utf-8")

    result = service.index_repository(project_id, repo)
    hit = service.search(project_id, "hybrid recall", limit=1)[0]

    assert result["indexed_files"] == 1
    assert hit["document"]["relative_path"] == "src/retrieval.py"
    assert "#lines=1-2&chunk=" in hit["reference"]
    assert not service.search(project_id, "ignored", limit=5)

    document_id = result["documents"][0]["id"]
    (repo / "src" / "retrieval.py").write_text(
        "def fuse():\n    return 'reranked precision'\n", encoding="utf-8"
    )
    rebuilt = service.reindex_document(project_id, document_id)

    assert rebuilt["status"] == "reindexed"
    assert (
        service.search(project_id, "reranked precision", limit=1)[0]["document"]["id"]
        == document_id
    )
