"""Notes index and object store. Qdrant/MinIO in production; in-memory fakes in tests."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx

from ..errors import Transient

log = logging.getLogger(__name__)


_NOTE_LISTING = re.compile(
    r"^(please\s+)?((summarize|list|show|read|get)\s+)?(the\s+|this\s+|all\s+)?"
    r"(latest\s+|recent\s+|authorized\s+)?(clinical\s+)?notes?\s*\.?$",
    re.I,
)


def is_notes_listing(question: str) -> bool:
    """True when the question is asking to browse or summarize notes, not a topic search."""
    q = (question or "").strip()
    return not q or bool(_NOTE_LISTING.match(q))


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

    async def delete_note(self, patient_key: str, note_id: str) -> None: ...


class ObjectStore(Protocol):
    async def put(self, bucket: str, key: str, data: bytes, *, content_type: str = "text/plain") -> str: ...

    async def get(self, bucket: str, key: str) -> bytes | None: ...

    async def list_prefix(self, bucket: str, prefix: str) -> list[str]: ...

    async def delete(self, bucket: str, key: str) -> None: ...


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

    async def delete_note(self, patient_key: str, note_id: str) -> None:
        self.chunks = [
            chunk
            for chunk in self.chunks
            if not (
                chunk.get("patient_key") == patient_key
                and note_id in {chunk.get("note_id"), chunk.get("sanitized_ref")}
            )
        ]


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

    async def delete(self, bucket: str, key: str) -> None:
        self.blobs.pop((bucket, key), None)


_EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _aws_signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    def sign(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    key = sign(f"AWS4{secret}".encode(), date_stamp)
    key = sign(key, region)
    key = sign(key, "s3")
    return sign(key, "aws4_request")


def _object_uri(bucket: str, key: str) -> str:
    parts = [quote(bucket, safe="")]
    parts.extend(quote(part, safe="") for part in key.split("/") if part)
    return "/" + "/".join(parts)


class MinioObjects:
    """Path-style S3 client for the MinIO `reports` bucket and its neighbors."""

    def __init__(self, url: str, access_key: str, secret_key: str, *, region: str = "us-east-1") -> None:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        self.endpoint = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        self.host = parsed.netloc
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

    def _headers(self, method: str, uri: str, payload: bytes, content_type: str) -> dict[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = amz_date[:8]
        payload_hash = hashlib.sha256(payload).hexdigest() if payload else _EMPTY_SHA
        canonical_headers = (
            f"content-type:{content_type}\n"
            f"host:{self.host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed = "content-type;host;x-amz-content-sha256;x-amz-date"
        canonical = "\n".join((method, uri, "", canonical_headers, signed, payload_hash))
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(
            (
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            )
        )
        signature = hmac.new(
            _aws_signing_key(self.secret_key, date_stamp, self.region),
            to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Host": self.host,
            "Content-Type": content_type,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={self.access_key}/{scope}, "
                f"SignedHeaders={signed}, "
                f"Signature={signature}"
            ),
        }

    async def _open(
        self, method: str, bucket: str, key: str, payload: bytes, content_type: str
    ) -> httpx.Response:
        uri = _object_uri(bucket, key)
        headers = self._headers(method, uri, payload, content_type)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                return await client.request(
                    method, f"{self.endpoint}{uri}", content=payload or None, headers=headers
                )
        except httpx.HTTPError as exc:
            log.error("object store %s failed: %s", method, exc.__class__.__name__)
            raise Transient("object store unavailable") from exc

    async def put(self, bucket: str, key: str, data: bytes, *, content_type: str = "text/plain") -> str:
        response = await self._open("PUT", bucket, key, data, content_type)
        if response.status_code >= 300:
            log.error("object store put http=%s", response.status_code)
            raise Transient("object store unavailable")
        return f"{bucket}/{key}"

    async def get(self, bucket: str, key: str) -> bytes | None:
        response = await self._open("GET", bucket, key, b"", "application/octet-stream")
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            log.error("object store get http=%s", response.status_code)
            raise Transient("object store unavailable")
        return response.content

    async def delete(self, bucket: str, key: str) -> None:
        response = await self._open("DELETE", bucket, key, b"", "application/octet-stream")
        if response.status_code in {200, 204, 404}:
            return
        log.error("object store delete http=%s", response.status_code)
        raise Transient("object store unavailable")

    async def list_prefix(self, bucket: str, prefix: str) -> list[str]:
        del bucket, prefix
        return []


class HttpNotes:
    def __init__(self, url: str, api_key: str, embed_url: str = "", embed_model: str = "") -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.embed_url = embed_url.rstrip("/")
        self.embed_model = embed_model or "nvidia/llama-nemotron-embed-vl-1b-v2"
        self.collection = "note_chunks"

    async def _embed(self, text: str, *, input_type: str) -> list[float] | None:
        if not self.embed_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{self.embed_url}/v1/embeddings",
                    json={
                        "model": self.embed_model,
                        "input": [text],
                        "input_type": input_type,
                        "truncate": "NONE",
                        "encoding_format": "float",
                    },
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
        if is_notes_listing(question):
            listed = await self._scroll(must, limit=max(limit, 32), exclude_internal=exclude_internal)
            uploaded = await self._scroll(
                [*must, {"key": "provenance", "match": {"value": "patient-reported"}}],
                limit=max(limit, 32),
                exclude_internal=exclude_internal,
            )
            clinician = await self._scroll(
                [*must, {"key": "source", "match": {"value": "upload"}}],
                limit=max(limit, 32),
                exclude_internal=exclude_internal,
            )
            return self._merge_rows(uploaded, clinician, listed)
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
        return self._payloads(hits, exclude_internal=exclude_internal)

    async def _scroll(
        self, must: list[dict[str, Any]], *, limit: int, exclude_internal: bool
    ) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{self.url}/collections/{self.collection}/points/scroll",
                    headers={"api-key": self.api_key},
                    json={"limit": limit, "with_payload": True, "filter": {"must": must}},
                )
                r.raise_for_status()
                hits = ((r.json().get("result") or {}).get("points") or [])
        except Exception as exc:
            log.error("qdrant scroll failed: %s", exc.__class__.__name__)
            raise Transient("notes index unavailable") from exc
        return self._payloads(hits, exclude_internal=exclude_internal)

    @staticmethod
    def _merge_rows(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in [row for group in groups for row in group]:
            key = str(row.get("point_id") or row.get("note_id") or row.get("cite_id") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(row)
        return out

    @staticmethod
    def _payloads(hits: list[dict[str, Any]], *, exclude_internal: bool) -> list[dict[str, Any]]:
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
        indexed: list[dict[str, Any]] = []
        for point in points:
            item = dict(point)
            if self.embed_url and not item.get("vector"):
                text = str((item.get("payload") or {}).get("text") or "")
                if text.strip():
                    vector = await self._embed(text, input_type="passage")
                    if vector:
                        item["vector"] = vector
            indexed.append(item)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.put(
                    f"{self.url}/collections/{collection}/points",
                    params={"wait": "true"},
                    headers={"api-key": self.api_key},
                    json={"points": indexed},
                )
                r.raise_for_status()
        except Transient:
            raise
        except Exception as exc:
            log.error("qdrant upsert failed: %s", exc.__class__.__name__)
            raise Transient("notes index unavailable") from exc

    async def delete_note(self, patient_key: str, note_id: str) -> None:
        body = {
            "filter": {
                "must": [
                    {"key": "patient_key", "match": {"value": patient_key}},
                    {"key": "note_id", "match": {"value": note_id}},
                ]
            }
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.url}/collections/{self.collection}/points/delete",
                    params={"wait": "true"},
                    headers={"api-key": self.api_key},
                    json=body,
                )
                response.raise_for_status()
        except Exception as exc:
            log.error("qdrant delete failed: %s", exc.__class__.__name__)
            raise Transient("notes index unavailable") from exc
