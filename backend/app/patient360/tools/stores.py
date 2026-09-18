"""Notes index and object store. Qdrant/MinIO in production; in-memory fakes in tests."""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import uuid4

import httpx

from ..errors import Transient

log = logging.getLogger(__name__)


class NotesIndex(Protocol):
    async def search(
        self,
        question: str,
        *,
        patient_key: str,
        published: bool = True,
        allowed_confidentiality: tuple[str, ...] | None = None,
        exclude_internal: bool = False,
        limit: int = 8,
    ) -> list[dict[str, Any]]: ...

    async def upsert(self, points: list[dict[str, Any]], *, collection: str = "note_chunks") -> None: ...


class ObjectStore(Protocol):
    async def put(self, bucket: str, key: str, data: bytes, *, content_type: str = "text/plain") -> str: ...

    async def get(self, bucket: str, key: str) -> bytes | None: ...

    async def list_prefix(self, bucket: str, prefix: str) -> list[str]: ...


class MemoryNotes:
    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self.chunks = list(chunks or [])
        self.calls: list[dict[str, Any]] = []

    async def search(
        self,
        question: str,
        *,
        patient_key: str,
        published: bool = True,
        allowed_confidentiality: tuple[str, ...] | None = None,
        exclude_internal: bool = False,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "question": question,
                "patient_key": patient_key,
                "published": published,
                "allowed_confidentiality": allowed_confidentiality,
                "exclude_internal": exclude_internal,
            }
        )
        q = question.lower()
        out: list[dict[str, Any]] = []
        for chunk in self.chunks:
            if chunk.get("patient_key") != patient_key:
                continue
            if published and not chunk.get("published", False):
                continue
            if (
                allowed_confidentiality is not None
                and chunk.get("confidentiality") not in allowed_confidentiality
            ):
                continue
            if exclude_internal and chunk.get("internal"):
                continue
            text = str(chunk.get("text") or "")
            words = [w for w in q.split() if len(w) > 3]
            score = 1.0 if not q or q in text.lower() or any(w in text.lower() for w in words) else 0.2
            row = dict(chunk)
            row["score"] = score
            out.append(row)
        out.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
        return out[:limit]

    async def upsert(self, points: list[dict[str, Any]], *, collection: str = "note_chunks") -> None:
        del collection
        for point in points:
            payload = dict(point.get("payload") or point)
            payload.setdefault("point_id", point.get("id") or str(uuid4()))
            self.chunks.append(payload)


class MemoryObjects:
    def __init__(self) -> None:
        self.blobs: dict[tuple[str, str], bytes] = {}

    async def put(self, bucket: str, key: str, data: bytes, *, content_type: str = "text/plain") -> str:
        del content_type
        self.blobs[(bucket, key)] = data
        return f"{bucket}/{key}"

    async def get(self, bucket: str, key: str) -> bytes | None:
        return self.blobs.get((bucket, key))

    async def list_prefix(self, bucket: str, prefix: str) -> list[str]:
        return [k for (b, k) in self.blobs if b == bucket and k.startswith(prefix)]


class HttpNotes:
    def __init__(self, url: str, api_key: str, embed_url: str = "") -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.embed_url = embed_url.rstrip("/")
        self.collection = "note_chunks"

    async def _embed(self, text: str, *, input_type: str) -> list[float] | None:
        if not self.embed_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{self.embed_url}/v1/embeddings",
                    json={"input": [text], "input_type": input_type, "truncate": "NONE"},
                )
                r.raise_for_status()
                data = r.json()
            return data["data"][0]["embedding"]
        except Exception as exc:
            log.error("embed failed: %s", exc.__class__.__name__)
            raise Transient("embed unavailable") from exc

    async def search(
        self,
        question: str,
        *,
        patient_key: str,
        published: bool = True,
        allowed_confidentiality: tuple[str, ...] | None = None,
        exclude_internal: bool = False,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = [
            {"key": "patient_key", "match": {"value": patient_key}},
            {"key": "published", "match": {"value": published}},
        ]
        if allowed_confidentiality is not None:
            must.append({"key": "confidentiality", "match": {"any": list(allowed_confidentiality)}})
        if exclude_internal:
            must.append({"key": "internal", "match": {"value": False}})
        vector = await self._embed(question, input_type="query")
        body: dict[str, Any] = {
            "limit": limit,
            "with_payload": True,
            "filter": {"must": must},
        }
        if vector is not None:
            body["vector"] = vector
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{self.url}/collections/{self.collection}/points/search",
                    headers={"api-key": self.api_key},
                    json=body,
                )
                r.raise_for_status()
                hits = r.json().get("result") or []
        except Transient:
            raise
        except Exception as exc:
            log.error("qdrant search failed: %s", exc.__class__.__name__)
            raise Transient("notes index unavailable") from exc
        out: list[dict[str, Any]] = []
        for hit in hits:
            payload = dict(hit.get("payload") or {})
            if exclude_internal and payload.get("internal"):
                continue
            payload["score"] = hit.get("score")
            payload["point_id"] = hit.get("id")
            out.append(payload)
        return out

    async def upsert(self, points: list[dict[str, Any]], *, collection: str = "note_chunks") -> None:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.put(
                    f"{self.url}/collections/{collection}/points",
                    params={"wait": "true"},
                    headers={"api-key": self.api_key},
                    json={"points": points},
                )
                r.raise_for_status()
        except Exception as exc:
            log.error("qdrant upsert failed: %s", exc.__class__.__name__)
            raise Transient("notes index unavailable") from exc
