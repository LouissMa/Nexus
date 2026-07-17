from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class FastEmbedProvider:
    provider_name = "fastembed"

    def __init__(self, model_name: str, cache_dir: Path | None = None):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model: Any = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prepared = [self._prepare(text, "passage") for text in texts]
        return self._embed(prepared)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._prepare(text, "query")])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            if self._model is None:
                from fastembed import TextEmbedding

                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=r"The model .* now uses mean pooling instead of CLS embedding.*",
                        category=UserWarning,
                    )
                    self._model = TextEmbedding(
                        model_name=self.model_name,
                        cache_dir=str(self.cache_dir) if self.cache_dir else None,
                        lazy_load=True,
                    )
            return [vector.tolist() for vector in self._model.embed(texts)]
        except (ImportError, ModuleNotFoundError) as exc:
            raise EmbeddingError(
                "FastEmbed is not installed. Run `python -m pip install -e .[rag]`."
            ) from exc
        except Exception as exc:
            raise EmbeddingError(f"FastEmbed failed: {exc}") from exc

    def _prepare(self, text: str, role: str) -> str:
        if "e5" in self.model_name.lower():
            return f"{role}: {text}"
        return text


class OpenAICompatibleEmbeddingProvider:
    provider_name = "openai_compatible"

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str,
        timeout_seconds: int = 30,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._request(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._request([text])[0]

    def _request(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingError("Embedding API key is not configured.")
        payload = json.dumps({"model": self.model_name, "input": texts}).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/embeddings",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise EmbeddingError(f"Embedding API returned HTTP {exc.code}: {detail}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EmbeddingError(f"Embedding API request failed: {exc}") from exc

        data = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") for item in data]
        if len(vectors) != len(texts) or any(not isinstance(vector, list) for vector in vectors):
            raise EmbeddingError("Embedding API returned an invalid response.")
        return [[float(value) for value in vector] for vector in vectors]
