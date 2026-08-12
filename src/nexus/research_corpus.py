from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .rag import LocalMemoryEmbedder
from .store import JsonStore


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_WEB_BYTES = 5 * 1024 * 1024
MAX_CHUNK_CHARS = 1_200
MAX_REPOSITORY_FILES = 500
MAX_REPOSITORY_BYTES = 50 * 1024 * 1024
TEXT_EXTENSIONS = {".txt": "text", ".md": "markdown", ".markdown": "markdown"}
REPOSITORY_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sh",
    ".ps1",
    ".sql",
    ".ipynb",
}
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".nexus",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}


class CorpusError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _hash(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return sha256(raw).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        clean = re.sub(r"\s+", " ", data).strip()
        if not clean:
            return
        if self._in_title:
            self.title = f"{self.title} {clean}".strip()[:500]
        else:
            self.parts.append(clean)

    def text(self) -> str:
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in " ".join(self.parts).splitlines()
        ]
        return "\n".join(line for line in lines if line)


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, validator: Callable[[str], str]):
        self.validator = validator
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return super().redirect_request(
            req, fp, code, msg, headers, self.validator(newurl)
        )


class ResearchCorpus:
    def __init__(
        self,
        store: JsonStore,
        *,
        index_root: Path | None = None,
        pdf_reader: Callable[[Path], list[tuple[int, str]]] | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.store = store
        self.index_root = index_root or store.path.parent / "research_corpus"
        self.pdf_reader = pdf_reader or self._read_pdf
        self.resolver = resolver or self._resolve_host
        self.embedder = LocalMemoryEmbedder()

    def ingest_file(self, project_id: str, path: str | Path) -> dict[str, Any]:
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            raise CorpusError(f"Document '{target}' is not a file.")
        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            raise CorpusError(f"Document exceeds the {MAX_FILE_BYTES} byte limit.")
        suffix = target.suffix.lower()
        if suffix == ".pdf":
            kind = "pdf"
            raw = target.read_bytes()
            chunks = self._pdf_chunks(self.pdf_reader(target))
        elif suffix in TEXT_EXTENSIONS:
            kind = TEXT_EXTENSIONS[suffix]
            raw = target.read_bytes()
            chunks = self._line_chunks(self._decode_text(raw))
        else:
            raise CorpusError("Supported document types are PDF, Markdown, and TXT.")
        return self._store_document(
            project_id,
            kind=kind,
            title=target.name,
            locator=str(target),
            content_hash=_hash(raw),
            chunks=chunks,
            metadata={"size_bytes": size},
        )

    def ingest_web(
        self,
        project_id: str,
        url: str,
        *,
        fetcher: Callable[[str, int], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        safe_url = self._validate_url(url)
        response = (fetcher or self._fetch_https)(safe_url, MAX_WEB_BYTES)
        final_url = self._validate_url(str(response.get("url") or safe_url))
        body = response.get("body")
        if not isinstance(body, bytes) or len(body) > MAX_WEB_BYTES:
            raise CorpusError("Web response is missing or exceeds the response limit.")
        content_type = str(response.get("content_type") or "").casefold()
        if "html" not in content_type and "text/plain" not in content_type:
            raise CorpusError("Only HTML and plain-text web responses are supported.")
        decoded = self._decode_text(body)
        if "html" in content_type:
            parser = _HTMLTextParser()
            parser.feed(decoded)
            text = parser.text()
            title = parser.title or urlparse(final_url).netloc
        else:
            text = decoded
            title = urlparse(final_url).netloc
        if not text.strip():
            raise CorpusError("The web page contains no extractable text.")
        return self._store_document(
            project_id,
            kind="web",
            title=title,
            locator=final_url,
            content_hash=_hash(body),
            chunks=self._line_chunks(text),
            metadata={"content_type": content_type[:200], "acquired_at": _now()},
        )

    def index_repository(self, project_id: str, root: str | Path) -> dict[str, Any]:
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise CorpusError("Repository root must be a directory.")
        indexed: list[dict[str, Any]] = []
        total_bytes = 0
        candidates = sorted(base.rglob("*"), key=lambda item: item.as_posix())
        for path in candidates:
            if len(indexed) >= MAX_REPOSITORY_FILES:
                break
            if any(
                part in IGNORED_DIRECTORIES for part in path.relative_to(base).parts
            ):
                continue
            if not path.is_file() or path.suffix.lower() not in REPOSITORY_EXTENSIONS:
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(base):
                continue
            size = resolved.stat().st_size
            if size > 1_000_000 or total_bytes + size > MAX_REPOSITORY_BYTES:
                continue
            raw = resolved.read_bytes()
            try:
                text = self._decode_text(raw)
            except CorpusError:
                continue
            relative = resolved.relative_to(base).as_posix()
            result = self._store_document(
                project_id,
                kind="repository",
                title=relative,
                locator=f"repo:{_hash(str(base))[:12]}:{relative}",
                content_hash=_hash(raw),
                chunks=self._line_chunks(text),
                metadata={
                    "repository": base.name,
                    "repository_root": str(base),
                    "relative_path": relative,
                    "source_path": str(resolved),
                    "size_bytes": size,
                },
            )
            indexed.append(result["document"])
            total_bytes += size
        return {
            "project_id": project_id,
            "repository": base.name,
            "indexed_files": len(indexed),
            "total_bytes": total_bytes,
            "documents": indexed,
        }

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        project = self._project(project_id)
        return deepcopy(project.get("documents", []))

    def show_document(self, project_id: str, document_id: str) -> dict[str, Any]:
        document = self._document(self._project(project_id), document_id)
        return deepcopy(document)

    def remove_document(self, project_id: str, document_id: str) -> dict[str, Any]:
        def mutation(state: dict[str, Any]) -> dict[str, Any]:
            project = self._project_from_state(state, project_id)
            documents = project.setdefault("documents", [])
            before = len(documents)
            documents[:] = [item for item in documents if item.get("id") != document_id]
            if len(documents) == before:
                raise CorpusError(f"Document '{document_id}' not found.")
            project["updated_at"] = _now()
            return {
                "project_id": project_id,
                "document_id": document_id,
                "removed": True,
            }

        result = self.store.mutate(mutation)
        self._index_path(project_id, document_id).unlink(missing_ok=True)
        return result

    def reindex_document(self, project_id: str, document_id: str) -> dict[str, Any]:
        document = self.show_document(project_id, document_id)
        if document["kind"] == "web":
            raise CorpusError("Web documents must be acquired again with web-add.")
        if document["kind"] == "repository":
            metadata = document.get("metadata", {})
            target = Path(str(metadata.get("source_path") or "")).resolve()
            root = Path(str(metadata.get("repository_root") or "")).resolve()
            if not target.is_file() or not target.is_relative_to(root):
                raise CorpusError("Repository document escaped its indexed root.")
            raw = target.read_bytes()
            if len(raw) > 1_000_000:
                raise CorpusError("Repository document exceeds the file limit.")
            return self._store_document(
                project_id,
                kind="repository",
                title=document["title"],
                locator=document["locator"],
                content_hash=_hash(raw),
                chunks=self._line_chunks(self._decode_text(raw)),
                metadata={**metadata, "size_bytes": len(raw)},
            )
        path = document.get("metadata", {}).get("source_path") or document["locator"]
        result = self.ingest_file(project_id, path)
        if result["document"]["id"] != document_id:
            raise CorpusError("Document identity changed during re-index.")
        return result

    def search(
        self, project_id: str, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        clean = str(query).strip()
        if not clean:
            raise CorpusError("Search query is required.")
        query_vector = self.embedder.embed(clean)
        scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for document in self.list_documents(project_id):
            payload = self._load_index(project_id, document["id"])
            for chunk in payload.get("chunks", []):
                score = self.embedder.similarity(query_vector, chunk.get("vector", {}))
                if score > 0:
                    scored.append((score, chunk, document))
        scored.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [
            {
                "text": chunk["text"],
                "reference": chunk["reference"],
                "score": round(score, 6),
                "document": self._public_document(document),
            }
            for score, chunk, document in scored[: max(1, min(int(limit), 20))]
        ]

    def validate_reference(self, reference: str) -> dict[str, Any]:
        match = re.fullmatch(
            r"document:([a-f0-9]{12})#.+&chunk=([a-f0-9]{16})", reference
        )
        if not match:
            return {"valid": False, "reason": "invalid_reference"}
        document_id, chunk_id = match.groups()
        for path in self.index_root.glob(f"*/{document_id}.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for chunk in payload.get("chunks", []):
                if chunk.get("id") != chunk_id:
                    continue
                if chunk.get("reference") != reference:
                    return {"valid": False, "reason": "reference_mismatch"}
                if chunk.get("content_hash") != _hash(str(chunk.get("text", ""))):
                    return {"valid": False, "reason": "content_hash_mismatch"}
                return {"valid": True, "reason": None, "chunk": deepcopy(chunk)}
        return {"valid": False, "reason": "missing_chunk"}

    def _store_document(
        self,
        project_id: str,
        *,
        kind: str,
        title: str,
        locator: str,
        content_hash: str,
        chunks: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not chunks:
            raise CorpusError("Document contains no extractable text.")
        self._project(project_id)
        document_id = _hash(f"{project_id}:{locator}")[:12]
        existing = next(
            (
                item
                for item in self.list_documents(project_id)
                if item.get("id") == document_id
            ),
            None,
        )
        if existing and existing.get("content_hash") == content_hash:
            return {"status": "unchanged", "document": existing}
        enriched = []
        for position, raw in enumerate(chunks, 1):
            text = raw["text"].strip()
            chunk_id = _hash(f"{document_id}:{position}:{text}")[:16]
            if kind == "pdf":
                location = f"page={raw['page']}"
            else:
                location = f"lines={raw['start_line']}-{raw['end_line']}"
            reference = f"document:{document_id}#{location}&chunk={chunk_id}"
            enriched.append(
                {
                    **raw,
                    "id": chunk_id,
                    "document_id": document_id,
                    "text": text,
                    "content_hash": _hash(text),
                    "reference": reference,
                    "vector": self.embedder.embed(text),
                }
            )
        timestamp = _now()
        document = {
            "id": document_id,
            "kind": kind,
            "title": str(title)[:500],
            "locator": str(locator)[:2_000],
            "content_hash": content_hash,
            "chunk_count": len(enriched),
            "metadata": deepcopy(metadata),
            "created_at": existing.get("created_at", timestamp)
            if existing
            else timestamp,
            "updated_at": timestamp,
        }
        index_path = self._index_path(project_id, document_id)
        previous = index_path.read_bytes() if index_path.exists() else None
        _atomic_json(index_path, {"document": document, "chunks": enriched})
        try:

            def mutation(state: dict[str, Any]) -> dict[str, Any]:
                project = self._project_from_state(state, project_id)
                documents = project.setdefault("documents", [])
                documents[:] = [
                    item for item in documents if item.get("id") != document_id
                ]
                documents.append(deepcopy(document))
                project["updated_at"] = timestamp
                return deepcopy(document)

            stored = self.store.mutate(mutation)
        except Exception:
            if previous is None:
                index_path.unlink(missing_ok=True)
            else:
                index_path.write_bytes(previous)
            raise
        return {
            "status": "indexed" if existing is None else "reindexed",
            "document": stored,
        }

    @staticmethod
    def _line_chunks(text: str) -> list[dict[str, Any]]:
        lines = text.splitlines() or [text]
        chunks: list[dict[str, Any]] = []
        buffer: list[str] = []
        start = 1
        for number, line in enumerate(lines, 1):
            candidate = "\n".join([*buffer, line]).strip()
            if buffer and len(candidate) > MAX_CHUNK_CHARS:
                chunks.append(
                    {
                        "text": "\n".join(buffer),
                        "start_line": start,
                        "end_line": number - 1,
                    }
                )
                buffer = [line]
                start = number
            else:
                buffer.append(line)
        if any(item.strip() for item in buffer):
            chunks.append(
                {"text": "\n".join(buffer), "start_line": start, "end_line": len(lines)}
            )
        return chunks

    @staticmethod
    def _pdf_chunks(pages: list[tuple[int, str]]) -> list[dict[str, Any]]:
        chunks = []
        for page, text in pages:
            clean = str(text or "").strip()
            for offset in range(0, len(clean), MAX_CHUNK_CHARS):
                part = clean[offset : offset + MAX_CHUNK_CHARS].strip()
                if part:
                    chunks.append({"text": part, "page": int(page)})
        return chunks

    @staticmethod
    def _decode_text(raw: bytes) -> str:
        if b"\x00" in raw[:4096]:
            raise CorpusError("Document is not valid UTF-8 text.")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorpusError("Document is not valid UTF-8 text.") from exc

    @staticmethod
    def _read_pdf(path: Path) -> list[tuple[int, str]]:
        try:
            from pypdf import PdfReader
        except (ImportError, ModuleNotFoundError) as exc:
            raise CorpusError(
                "PDF support is not installed. Run `python -m pip install -e .[research]`."
            ) from exc
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise CorpusError("Encrypted PDFs are not supported.")
            return [
                (index, page.extract_text() or "")
                for index, page in enumerate(reader.pages, 1)
            ]
        except CorpusError:
            raise
        except Exception as exc:
            raise CorpusError(f"PDF extraction failed: {exc}") from exc

    def _validate_url(self, raw: str) -> str:
        parsed = urlparse(str(raw).strip())
        if parsed.scheme.casefold() != "https" or not parsed.hostname:
            raise CorpusError("Web acquisition requires an HTTPS URL.")
        if parsed.username or parsed.password:
            raise CorpusError("Credentials are not allowed in web URLs.")
        if parsed.port not in {None, 443}:
            raise CorpusError("Only the default HTTPS port is allowed.")
        host = parsed.hostname.casefold().rstrip(".")
        if host == "localhost" or host.endswith(".localhost"):
            raise CorpusError("Local network destinations are not allowed.")
        try:
            addresses = self.resolver(host)
        except OSError as exc:
            raise CorpusError("Web host could not be resolved safely.") from exc
        if not addresses:
            raise CorpusError("Web host did not resolve to an address.")
        for raw_address in addresses:
            address = ipaddress.ip_address(raw_address)
            if not address.is_global:
                raise CorpusError(
                    "Private or reserved network destinations are not allowed."
                )
        return urlunparse(
            ("https", parsed.netloc, parsed.path or "/", "", parsed.query, "")
        )

    @staticmethod
    def _resolve_host(host: str) -> list[str]:
        return sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        )

    def _fetch_https(self, url: str, limit: int) -> dict[str, Any]:
        opener = build_opener(_SafeRedirect(self._validate_url))
        request = Request(
            url,
            headers={
                "User-Agent": "Nexus-Research/2.0",
                "Accept": "text/html,text/plain",
            },
        )
        try:
            with opener.open(request, timeout=20) as response:
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise CorpusError("Web response exceeds the response limit.")
                return {
                    "url": response.geturl(),
                    "content_type": response.headers.get("Content-Type", ""),
                    "body": body,
                }
        except CorpusError:
            raise
        except Exception as exc:
            raise CorpusError(f"Web acquisition failed: {type(exc).__name__}") from exc

    def _index_path(self, project_id: str, document_id: str) -> Path:
        return self.index_root / project_id / f"{document_id}.json"

    def _load_index(self, project_id: str, document_id: str) -> dict[str, Any]:
        path = self._index_path(project_id, document_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorpusError(
                f"Document index '{document_id}' is unavailable."
            ) from exc
        return payload if isinstance(payload, dict) else {}

    def _project(self, project_id: str) -> dict[str, Any]:
        return deepcopy(self._project_from_state(self.store.load(), project_id))

    @staticmethod
    def _project_from_state(state: dict[str, Any], project_id: str) -> dict[str, Any]:
        for project in state.get("research_projects", []):
            if isinstance(project, dict) and project.get("id") == project_id:
                if project.get("status") == "archived":
                    raise CorpusError("Archived research projects cannot be changed.")
                return project
        raise CorpusError(f"Research project '{project_id}' not found.")

    @staticmethod
    def _document(project: dict[str, Any], document_id: str) -> dict[str, Any]:
        for document in project.get("documents", []):
            if isinstance(document, dict) and document.get("id") == document_id:
                return document
        raise CorpusError(f"Document '{document_id}' not found.")

    @staticmethod
    def _public_document(document: dict[str, Any]) -> dict[str, Any]:
        metadata = document.get("metadata", {})
        return {
            "id": document.get("id"),
            "kind": document.get("kind"),
            "title": document.get("title"),
            "chunk_count": document.get("chunk_count", 0),
            "relative_path": metadata.get("relative_path")
            if isinstance(metadata, dict)
            else None,
        }
