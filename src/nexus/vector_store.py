from __future__ import annotations

import atexit

from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


class VectorStoreError(RuntimeError):
    pass


class QdrantVectorStore:
    def __init__(
        self,
        collection_name: str,
        path: Path | None = None,
        url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 30,
        location: str | None = None,
    ):
        self.collection_name = collection_name
        self.path = path
        self.url = url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.location = location
        self._client: Any = None

    def upsert(
        self,
        memories: list[dict[str, Any]],
        vectors: list[list[float]],
        recreate: bool = False,
    ) -> int:
        if len(memories) != len(vectors):
            raise VectorStoreError("Memory/vector count mismatch.")
        if not memories:
            return 0
        dimension = len(vectors[0])
        if dimension == 0 or any(len(vector) != dimension for vector in vectors):
            raise VectorStoreError("Embedding vectors must have one consistent non-zero dimension.")

        client, models = self._dependencies()
        self._ensure_collection(client, models, dimension, recreate)
        points = [
            models.PointStruct(
                id=self._point_id(memory["id"]),
                vector=vector,
                payload=self._payload(memory),
            )
            for memory, vector in zip(memories, vectors, strict=True)
        ]
        try:
            client.upsert(collection_name=self.collection_name, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc
        return len(points)

    def close(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        try:
            client.close()
        except Exception:
            pass

    def clear(self) -> None:
        client, _ = self._dependencies()
        try:
            if client.collection_exists(self.collection_name):
                client.delete_collection(self.collection_name)
        except Exception as exc:
            raise VectorStoreError(f"Qdrant clear failed: {exc}") from exc

    def search(self, vector: list[float], limit: int) -> list[dict[str, Any]]:
        client, _ = self._dependencies()
        try:
            if not client.collection_exists(self.collection_name):
                return []
            response = client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=max(1, limit),
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc

        results: list[dict[str, Any]] = []
        for point in response.points:
            payload = dict(point.payload or {})
            payload["dense_score"] = round(float(point.score), 6)
            results.append(payload)
        return results

    def status(self) -> dict[str, Any]:
        client, _ = self._dependencies()
        try:
            if not client.collection_exists(self.collection_name):
                return {"available": True, "collection_exists": False, "count": 0}
            count = client.count(collection_name=self.collection_name, exact=True).count
            return {"available": True, "collection_exists": True, "count": int(count)}
        except Exception as exc:
            raise VectorStoreError(f"Qdrant status failed: {exc}") from exc

    def _ensure_collection(self, client: Any, models: Any, dimension: int, recreate: bool) -> None:
        try:
            exists = client.collection_exists(self.collection_name)
            if recreate and exists:
                client.delete_collection(self.collection_name)
                exists = False
            if exists:
                info = client.get_collection(self.collection_name)
                configured = info.config.params.vectors
                existing_size = getattr(configured, "size", None)
                if existing_size is not None and int(existing_size) != dimension:
                    raise VectorStoreError(
                        "Embedding dimension changed. Run `nexus memory reindex` to recreate the index."
                    )
                return
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Qdrant collection setup failed: {exc}") from exc

    def _dependencies(self) -> tuple[Any, Any]:
        if self._client is not None:
            from qdrant_client import models

            return self._client, models
        try:
            from qdrant_client import QdrantClient, models
        except (ImportError, ModuleNotFoundError) as exc:
            raise VectorStoreError(
                "Qdrant client is not installed. Run `python -m pip install -e .[rag]`."
            ) from exc

        try:
            if self.location:
                self._client = QdrantClient(location=self.location)
            elif self.url:
                self._client = QdrantClient(
                    url=self.url,
                    api_key=self.api_key,
                    timeout=self.timeout_seconds,
                )
            else:
                if self.path is None:
                    raise VectorStoreError("A Qdrant path or URL is required.")
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(self.path))
            atexit.register(self.close)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Qdrant initialization failed: {exc}") from exc
        return self._client, models

    @staticmethod
    def _point_id(memory_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"nexus-memory:{memory_id}"))

    @staticmethod
    def _payload(memory: dict[str, Any]) -> dict[str, Any]:
        payload = dict(memory)
        payload.pop("embedding", None)
        payload["memory_id"] = payload.get("id")
        return payload
