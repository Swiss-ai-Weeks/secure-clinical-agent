from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from patient360.dicom import MemoryDicom, OrthancStore, _first_instance, parse_dicomweb_path
from patient360.main import create_app

from .conftest import make_deps, make_settings

STUDY_UID = "1.2.840.study"
SERIES_JSON = b'[{"SeriesInstanceUID":"1.2.840.series"}]'


def test_first_instance_from_id_list():
    assert _first_instance(["abc", "def"]) == "abc"


def test_first_instance_from_objects():
    assert _first_instance([{"ID": "study-row"}]) == "study-row"


def test_first_instance_empty():
    assert _first_instance([]) is None
    assert _first_instance({}) is None


@pytest.mark.asyncio
async def test_memory_preview_roundtrip():
    store = MemoryDicom({"s1": b"PNG"})
    assert await store.preview("s1") == b"PNG"
    assert await store.preview("missing") is None


@pytest.mark.asyncio
async def test_orthanc_preview_uses_first_instance():
    store = OrthancStore("http://orthanc.test", "u", "p")
    listed = Mock(status_code=200)
    listed.json.return_value = ["inst-1"]
    listed.raise_for_status = Mock()
    preview = Mock(status_code=200, content=b"png-bytes")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[listed, preview])
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    with patch("patient360.dicom.httpx.AsyncClient", return_value=client):
        assert await store.preview("study-1") == b"png-bytes"
    assert client.get.call_args_list[0].args[0].endswith("/studies/study-1/instances")
    assert client.get.call_args_list[1].args[0].endswith("/instances/inst-1/preview")


@pytest.mark.asyncio
async def test_orthanc_rejects_path_traversal():
    store = OrthancStore("http://orthanc.test", "u", "p")
    assert await store.preview("../system") is None
    assert await store.preview("a/b") is None


@pytest.mark.asyncio
async def test_media_fetch_prefers_dicom_store():
    settings = make_settings()
    deps, *_ = make_deps(settings, dicom=MemoryDicom({"study-1": b"PIXELS"}))
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "chen", "auth_level": 2})
        signed = await client.post("/media/sign", json={"patient_key": "p_101", "study_id": "study-1"})
        assert signed.status_code == 200, signed.text
        fetched = await client.get(signed.json()["url"])
        assert fetched.status_code == 200
        assert fetched.json()["length"] == 6


def test_parse_dicomweb_allows_one_study_and_rejects_patients():
    series = parse_dicomweb_path(f"studies/{STUDY_UID}/series")
    assert series is not None
    assert series.kind == "study"
    assert series.study_uid == STUDY_UID
    frame = parse_dicomweb_path(f"studies/{STUDY_UID}/series/1.2.840.series/instances/1.2.840.sop/frames/1")
    assert frame is not None
    assert frame.kind == "frame"
    assert parse_dicomweb_path("patients") is None
    assert parse_dicomweb_path("studies/../system") is None
    assert parse_dicomweb_path("studies") is not None


@pytest.mark.asyncio
async def test_orthanc_study_instance_uid_from_main_tags():
    store = OrthancStore("http://orthanc.test", "u", "p")
    listed = Mock(status_code=200)
    listed.json.return_value = {"MainDicomTags": {"StudyInstanceUID": STUDY_UID}}
    listed.raise_for_status = Mock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=listed)
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    with patch("patient360.dicom.httpx.AsyncClient", return_value=client):
        assert await store.study_instance_uid("study-1") == STUDY_UID
    assert await store.study_instance_uid("../system") is None
    assert await store.study_instance_uid("a/b") is None


@pytest.mark.asyncio
async def test_orthanc_dicomweb_rejects_traversal():
    store = OrthancStore("http://orthanc.test", "u", "p")
    assert await store.dicomweb("../system", {}) is None
    assert await store.dicomweb("studies/../patients", {}) is None


def _signed_store() -> MemoryDicom:
    return MemoryDicom(
        previews={"study-1": b"PIXELS"},
        study_uids={"study-1": STUDY_UID},
        dicomweb={
            "studies": (200, b"[]", "application/dicom+json"),
            f"studies/{STUDY_UID}/series": (200, SERIES_JSON, "application/dicom+json"),
            f"studies/{STUDY_UID}/series/1.2.840.series/instances/1.2.840.sop/frames/1": (
                200,
                b"FRAME",
                "multipart/related; type=application/octet-stream",
            ),
        },
    )


async def _sign_pixels(client: httpx.AsyncClient) -> dict:
    await client.post("/auth/dev-login", json={"login": "chen", "auth_level": 2})
    signed = await client.post("/media/sign", json={"patient_key": "p_101", "study_id": "study-1"})
    assert signed.status_code == 200, signed.text
    return signed.json()


def _token(url: str) -> str:
    return url.split("/")[2]


@pytest.mark.asyncio
async def test_media_sign_includes_study_instance_uid():
    settings = make_settings()
    deps, *_ = make_deps(settings, dicom=_signed_store())
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = await _sign_pixels(client)
        assert body["study_instance_uid"] == STUDY_UID
        preview = await client.get(body["url"])
        assert preview.status_code == 200
        assert preview.json()["length"] == 6
        patient = await client.get(f"/media/{_token(body['url'])}/Patient")
        assert patient.status_code == 404


@pytest.mark.asyncio
async def test_dicomweb_streams_signed_series():
    settings = make_settings()
    store = _signed_store()
    deps, audit, *_ = make_deps(settings, dicom=store)
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = await _sign_pixels(client)
        token = _token(body["url"])
        series = await client.get(
            f"/media/{token}/dicom-web/studies/{STUDY_UID}/series",
            params={"PatientName": "Keller", "StudyInstanceUID": STUDY_UID},
        )
        assert series.status_code == 200
        assert series.content == SERIES_JSON
        assert series.headers["content-type"].startswith("application/dicom+json")
        assert store.dicomweb_calls[-1][0] == f"studies/{STUDY_UID}/series"
        assert store.dicomweb_calls[-1][1]["StudyInstanceUID"] == STUDY_UID
        assert "PatientName" not in store.dicomweb_calls[-1][1]
        other = await client.get(f"/media/{token}/dicom-web/studies/9.9.9/series")
        assert other.status_code == 404
        patients = await client.get(f"/media/{token}/dicom-web/patients")
        assert patients.status_code == 404
        qido = await client.get(f"/media/{token}/dicom-web/studies", params={"StudyInstanceUID": "9.9.9"})
        assert qido.status_code == 404
        frames = await client.get(
            f"/media/{token}/dicom-web/studies/{STUDY_UID}/series/1.2.840.series/instances/1.2.840.sop/frames/1"
        )
        assert frames.status_code == 200
        assert frames.content == b"FRAME"
    fetches = [event for _, event in audit.events if event.event_type == "media_fetch"]
    assert [event.outcome_desc for event in fetches] == ["dicom-web"]
    assert fetches[0].entity_resource == STUDY_UID


@pytest.mark.asyncio
async def test_dicomweb_document_token_is_404():
    settings = make_settings()
    deps, *_ = make_deps(settings, dicom=_signed_store())
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "chen", "auth_level": 2})
        signed = await client.post(
            "/media/sign", json={"patient_key": "p_101", "object_key": "notes/p_101/report.pdf"}
        )
        assert signed.status_code == 200, signed.text
        token = _token(signed.json()["url"])
        denied = await client.get(f"/media/{token}/dicom-web/studies/{STUDY_UID}/series")
        assert denied.status_code == 404


@pytest.mark.asyncio
async def test_dicomweb_cross_session_is_401():
    settings = make_settings()
    deps, *_ = make_deps(settings, dicom=_signed_store())
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = await _sign_pixels(client)
        token = _token(body["url"])
        other = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        await other.post("/auth/dev-login", json={"login": "okafor", "on_duty": True, "auth_level": 2})
        replay = await other.get(f"/media/{token}/dicom-web/studies/{STUDY_UID}/series")
        await other.aclose()
        assert replay.status_code == 401
