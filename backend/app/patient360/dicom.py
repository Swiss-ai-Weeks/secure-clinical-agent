"""Orthanc-backed DICOM study access. Pixels never go through agent tools."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from .vista_overlay import SERIES_DESCRIPTION

_UID = re.compile(r"^[0-9A-Za-z._-]{1,64}$")
_FRAME = re.compile(r"^[0-9]{1,6}$")
_LEAF = frozenset({"metadata", "thumbnail", "rendered"})
_DROP_QUERY = frozenset(
    {
        "patientname",
        "patientid",
        "patientbirthdate",
        "00100010",
        "00100020",
        "00100030",
    }
)
_KEEP_QUERY = frozenset(
    {
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "SOPInstanceUID",
        "includefield",
        "includeField",
        "limit",
        "offset",
        "fuzzymatching",
        "requestType",
        "studyUID",
        "seriesUID",
        "objectUID",
        "contentType",
        "frameNumber",
        "rows",
        "columns",
        "windowCenter",
        "windowWidth",
        "imageQuality",
        "annotation",
    }
)


@dataclass(frozen=True)
class DicomWebPath:
    kind: str
    study_uid: str | None
    series_uid: str | None
    upstream: str


@dataclass
class DicomWebResult:
    status_code: int
    content_type: str
    body: bytes | AsyncIterator[bytes]
    headers: dict[str, str] = field(default_factory=dict)


class DicomStore(Protocol):
    async def preview(self, study_id: str) -> bytes | None: ...

    async def study_instance_uid(self, study_id: str) -> str | None: ...

    async def dicomweb(self, path: str, query: Mapping[str, str]) -> DicomWebResult | None: ...

    async def export_ct(self, study_id: str, dest: Path | None = None) -> list[bytes]: ...

    async def store_instance(self, payload: bytes) -> dict[str, Any]: ...

    async def delete_vista_seg(self, study_id: str) -> int: ...


class MemoryDicom:
    def __init__(
        self,
        previews: dict[str, bytes] | None = None,
        study_uids: dict[str, str] | None = None,
        dicomweb: dict[str, tuple[int, bytes, str]] | None = None,
    ) -> None:
        self.previews = dict(previews or {})
        self.study_uids = dict(study_uids or {})
        self.dicomweb_map = dict(dicomweb or {})
        self.dicomweb_calls: list[tuple[str, dict[str, str]]] = []
        self.ct_files: dict[str, list[bytes]] = {}
        self.stored: list[bytes] = []
        self.deleted_vista: list[str] = []

    async def preview(self, study_id: str) -> bytes | None:
        return self.previews.get(study_id)

    async def study_instance_uid(self, study_id: str) -> str | None:
        if not _safe_id(study_id):
            return None
        return self.study_uids.get(study_id)

    async def dicomweb(self, path: str, query: Mapping[str, str]) -> DicomWebResult | None:
        self.dicomweb_calls.append((path, dict(query)))
        hit = self.dicomweb_map.get(path)
        if hit is None:
            return None
        status, content, content_type = hit
        return DicomWebResult(status_code=status, content_type=content_type, body=content)

    async def export_ct(self, study_id: str, dest: Path | None = None) -> list[bytes]:
        files = list(self.ct_files.get(study_id, []))
        if dest is not None:
            dest.mkdir(parents=True, exist_ok=True)
            for index, payload in enumerate(files, start=1):
                (dest / f"{index:04d}.dcm").write_bytes(payload)
        return files

    async def store_instance(self, payload: bytes) -> dict[str, Any]:
        self.stored.append(payload)
        return {"ParentStudy": "memory", "ID": f"stored-{len(self.stored)}"}

    async def delete_vista_seg(self, study_id: str) -> int:
        self.deleted_vista.append(study_id)
        return 1


class OrthancStore:
    """Study-scoped Orthanc REST. Never lists patients or searches by name."""

    def __init__(self, url: str, user: str, password: str, *, timeout: float = 20.0) -> None:
        self.url = url.rstrip("/")
        self.auth = (user, password)
        self.timeout = timeout

    async def preview(self, study_id: str) -> bytes | None:
        if not _safe_id(study_id):
            return None
        async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
            listed = await client.get(f"{self.url}/studies/{study_id}/instances")
            if listed.status_code == 404:
                return None
            listed.raise_for_status()
            instance_id = _first_instance(listed.json())
            if not instance_id:
                return None
            preview = await client.get(f"{self.url}/instances/{instance_id}/preview")
            if preview.status_code == 200 and preview.content:
                return preview.content
            raw = await client.get(f"{self.url}/instances/{instance_id}/file")
            if raw.status_code == 404:
                return None
            raw.raise_for_status()
            return raw.content or None

    async def study_instance_uid(self, study_id: str) -> str | None:
        if not _safe_id(study_id):
            return None
        async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
            listed = await client.get(f"{self.url}/studies/{study_id}")
            if listed.status_code == 404:
                return None
            listed.raise_for_status()
            body = listed.json()
            tags = body.get("MainDicomTags") if isinstance(body, dict) else None
            uid = tags.get("StudyInstanceUID") if isinstance(tags, dict) else None
            return str(uid) if uid else None

    async def dicomweb(self, path: str, query: Mapping[str, str]) -> DicomWebResult | None:
        if path != "wado" and not _safe_dicomweb_path(path):
            return None
        url = f"{self.url}/wado" if path == "wado" else f"{self.url}/dicom-web/{path}"
        client = httpx.AsyncClient(auth=self.auth, timeout=self.timeout)
        try:
            request = client.build_request("GET", url, params=dict(query))
            response = await client.send(request, stream=True)
        except Exception:
            await client.aclose()
            raise
        if response.status_code == 404:
            await response.aclose()
            await client.aclose()
            return None
        content_type = response.headers.get("content-type") or "application/octet-stream"

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return DicomWebResult(status_code=response.status_code, content_type=content_type, body=chunks())

    async def export_ct(self, study_id: str, dest: Path | None = None) -> list[bytes]:
        if not _safe_id(study_id):
            return []
        files: list[bytes] = []
        async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
            listed = await client.get(f"{self.url}/studies/{study_id}/series")
            if listed.status_code == 404:
                return []
            listed.raise_for_status()
            series = listed.json()
            if not isinstance(series, list):
                return []
            if dest is not None:
                dest.mkdir(parents=True, exist_ok=True)
            index = 0
            for row in series:
                if not isinstance(row, dict):
                    continue
                tags = row.get("MainDicomTags") if isinstance(row.get("MainDicomTags"), dict) else {}
                if str(tags.get("Modality") or "").upper() == "SEG":
                    continue
                series_id = str(row.get("ID") or "")
                if not series_id or not _safe_id(series_id):
                    continue
                instances = await client.get(f"{self.url}/series/{series_id}/instances")
                instances.raise_for_status()
                body = instances.json()
                if not isinstance(body, list):
                    continue
                for item in body:
                    ident = item if isinstance(item, str) else None
                    if ident is None and isinstance(item, dict):
                        ident = item.get("ID")
                    if not ident or not _safe_id(str(ident)):
                        continue
                    raw = await client.get(f"{self.url}/instances/{ident}/file")
                    if raw.status_code != 200 or not raw.content:
                        continue
                    files.append(raw.content)
                    if dest is not None:
                        index += 1
                        (dest / f"{index:04d}.dcm").write_bytes(raw.content)
        return files

    async def store_instance(self, payload: bytes) -> dict[str, Any]:
        async with httpx.AsyncClient(auth=self.auth, timeout=max(self.timeout, 60.0)) as client:
            stored = await client.post(
                f"{self.url}/instances",
                content=payload,
                headers={"Content-Type": "application/dicom"},
            )
            stored.raise_for_status()
            body = stored.json()
        if not isinstance(body, dict) or not body.get("ParentStudy"):
            raise RuntimeError("orthanc store did not return ParentStudy")
        return body

    async def delete_vista_seg(self, study_id: str) -> int:
        if not _safe_id(study_id):
            return 0
        removed = 0
        async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
            listed = await client.get(f"{self.url}/studies/{study_id}/series")
            if listed.status_code == 404:
                return 0
            listed.raise_for_status()
            series = listed.json()
            if not isinstance(series, list):
                return 0
            for row in series:
                if not isinstance(row, dict):
                    continue
                tags = row.get("MainDicomTags") if isinstance(row.get("MainDicomTags"), dict) else {}
                description = str(tags.get("SeriesDescription") or "")
                if str(tags.get("Modality") or "").upper() != "SEG":
                    continue
                if SERIES_DESCRIPTION not in description:
                    continue
                series_id = str(row.get("ID") or "")
                if not series_id or not _safe_id(series_id):
                    continue
                deleted = await client.delete(f"{self.url}/series/{series_id}")
                if deleted.status_code in (200, 204):
                    removed += 1
        return removed


def parse_dicomweb_path(rel: str) -> DicomWebPath | None:
    """Allow one study's QIDO/WADO paths. Reject patients, STOW, and traversal."""
    if ".." in rel or "\\" in rel or ":" in rel:
        return None
    parts = [item for item in rel.split("/") if item]
    if not parts:
        return DicomWebPath(kind="wado_uri", study_uid=None, series_uid=None, upstream="wado")
    if parts[0] != "studies":
        return None
    if len(parts) == 1:
        return DicomWebPath(kind="studies", study_uid=None, series_uid=None, upstream="studies")
    if not _UID.fullmatch(parts[1]):
        return None
    study = parts[1]
    if len(parts) == 2:
        return DicomWebPath(kind="study", study_uid=study, series_uid=None, upstream="/".join(parts))
    if parts[2] in _LEAF:
        if len(parts) != 3:
            return None
        return DicomWebPath(kind="study", study_uid=study, series_uid=None, upstream="/".join(parts))
    if parts[2] != "series":
        return None
    if len(parts) == 3:
        return DicomWebPath(kind="study", study_uid=study, series_uid=None, upstream="/".join(parts))
    if not _UID.fullmatch(parts[3]):
        return None
    series = parts[3]
    if len(parts) == 4:
        return DicomWebPath(kind="series", study_uid=study, series_uid=series, upstream="/".join(parts))
    if parts[4] in _LEAF:
        if len(parts) != 5:
            return None
        return DicomWebPath(kind="series", study_uid=study, series_uid=series, upstream="/".join(parts))
    if parts[4] != "instances":
        return None
    if len(parts) == 5:
        return DicomWebPath(kind="series", study_uid=study, series_uid=series, upstream="/".join(parts))
    if not _UID.fullmatch(parts[5]):
        return None
    if len(parts) == 6:
        return DicomWebPath(kind="series", study_uid=study, series_uid=series, upstream="/".join(parts))
    if parts[6] in _LEAF:
        if len(parts) != 7:
            return None
        return DicomWebPath(kind="series", study_uid=study, series_uid=series, upstream="/".join(parts))
    if parts[6] == "bulkdata":
        if not all(_UID.fullmatch(part) or part.isalnum() for part in parts[7:]):
            return None
        return DicomWebPath(kind="series", study_uid=study, series_uid=series, upstream="/".join(parts))
    if parts[6] != "frames":
        return None
    if len(parts) == 8 and _FRAME.fullmatch(parts[7]):
        return DicomWebPath(kind="frame", study_uid=study, series_uid=series, upstream="/".join(parts))
    if len(parts) == 9 and _FRAME.fullmatch(parts[7]) and parts[8] == "rendered":
        return DicomWebPath(kind="frame", study_uid=study, series_uid=series, upstream="/".join(parts))
    return None


def sanitize_dicomweb_query(raw: Mapping[str, str], *, study_uid: str, kind: str) -> dict[str, str] | None:
    """Keep one study. Drop patient identifiers and fuzzy / wildcard search."""
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key.lower() in _DROP_QUERY:
            continue
        if key.lower() == "fuzzymatching":
            out[key] = "false"
            continue
        if key not in _KEEP_QUERY:
            continue
        out[key] = value
    if out.get("StudyInstanceUID") and out["StudyInstanceUID"] != study_uid:
        return None
    if out.get("studyUID") and out["studyUID"] != study_uid:
        return None
    if kind == "studies":
        out["StudyInstanceUID"] = study_uid
    if kind == "wado_uri":
        if out.get("requestType") != "WADO":
            return None
        out["studyUID"] = study_uid
    return out


def _safe_id(study_id: str) -> bool:
    return bool(study_id) and all(token not in study_id for token in ("/", "\\", "..", ":"))


def _safe_dicomweb_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and all(token not in path for token in ("..", "\\", ":"))


def _first_instance(body: Any) -> str | None:
    if isinstance(body, list) and body:
        row = body[0]
        if isinstance(row, str) and row:
            return row
        if isinstance(row, dict):
            ident = row.get("ID") or row.get("id")
            if ident:
                return str(ident)
    return None
