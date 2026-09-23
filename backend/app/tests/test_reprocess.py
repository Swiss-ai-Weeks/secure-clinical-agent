from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from patient360.dicom import MemoryDicom
from patient360.main import create_app
from patient360.vista_overlay import OverlayResult

from .conftest import make_deps, make_settings


def _app(settings=None, **overrides):
    settings = settings or make_settings(vista_url="http://vista.test")
    deps, audit, *_rest = make_deps(settings, **overrides)
    clinical = deps.clinical
    clinical.study_rows.append(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "source_id": "seed-demo/ImagingStudy/p102-ct-2026-07-01",
            "patient_key": "p_102",
            "modality": "CT",
            "procedure_code": "24627-2",
            "procedure_display": "CT Chest",
            "orthanc_id": "ct-study-1",
        }
    )
    clinical.study_rows.append(
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "source_id": "seed-demo/ImagingStudy/p101-cxr-2026-09-11",
            "patient_key": "p_101",
            "modality": "CR",
            "procedure_display": "Chest X-ray",
            "orthanc_id": "cr-study-1",
        }
    )
    app = create_app(settings, deps)
    app.state.deps = deps
    return app, deps, audit


@pytest.mark.asyncio
async def test_chen_reprocess_ct_stores_overlay():
    dicom = MemoryDicom()
    dicom.ct_files["ct-study-1"] = [b"CT0", b"CT1"]
    app, deps, audit = _app(dicom=dicom)
    overlay = OverlayResult(
        seg_bytes=b"SEG",
        classes=("heart",),
        report_text="VISTA-3D overlay on CT: heart. Toggle the segmentation in the study viewer.",
        series_uid="2.25.vista",
    )
    with (
        patch("patient360.reprocess.vista_segment", return_value=b"mask"),
        patch("patient360.reprocess.build_overlay", return_value=overlay),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
            r = await client.post("/patients/p_102/studies/ct-study-1/reprocess", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classes"] == ["heart"]
    assert "heart" in body["report_text"]
    assert dicom.stored == [b"SEG"]
    assert "ct-study-1" in dicom.deleted_vista
    assert any(event.event_type == "vista_reprocess" for _, event in audit.events)
    assert deps.clinical.report_rows[-1]["conclusion_text"] == overlay.report_text


@pytest.mark.asyncio
async def test_agent_token_cannot_reprocess():
    app, *_ = _app(dicom=MemoryDicom())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
        token = (await client.post("/dev/run-token", json={})).json()["access_token"]
        r = await client.post(
            "/patients/p_102/studies/ct-study-1/reprocess",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_reprocess_rejects_non_ct():
    app, *_ = _app(dicom=MemoryDicom())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
        r = await client.post("/patients/p_101/studies/cr-study-1/reprocess", json={})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_reprocess_other_patient_study_is_404():
    app, *_ = _app(dicom=MemoryDicom())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
        r = await client.post("/patients/p_102/studies/cr-study-1/reprocess", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rivera_reprocess_is_404():
    app, *_ = _app(dicom=MemoryDicom())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "rivera", "on_duty": True, "auth_level": 2})
        r = await client.post("/patients/p_102/studies/ct-study-1/reprocess", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_agent_can_prompt_vista_classes():
    dicom = MemoryDicom()
    dicom.ct_files["ct-study-1"] = [b"CT0", b"CT1"]
    app, deps, audit = _app(dicom=dicom)
    overlay = OverlayResult(
        seg_bytes=b"SEG",
        classes=("liver",),
        report_text="VISTA-3D overlay on CT: liver. Toggle the segmentation in the study viewer.",
        series_uid="2.25.vista",
    )
    with (
        patch("patient360.reprocess.vista_segment", return_value=b"mask"),
        patch("patient360.reprocess.build_overlay", return_value=overlay),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
            token = (await client.post("/dev/run-token", json={})).json()["access_token"]
            r = await client.post(
                "/tools/imaging",
                json={"patient_key": "p_102", "study_id": "ct-study-1", "classes": ["liver"]},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overlay_classes"] == ["liver"]
    assert "liver" in body["overlay_text"]
    assert "pixel" not in json.dumps(body).lower()
    assert dicom.stored == [b"SEG"]
    assert any(event.event_type == "vista_reprocess" for _, event in audit.events)


@pytest.mark.asyncio
async def test_agent_unknown_vista_class_is_422():
    app, *_ = _app(dicom=MemoryDicom())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
        token = (await client.post("/dev/run-token", json={})).json()["access_token"]
        r = await client.post(
            "/tools/imaging",
            json={"patient_key": "p_102", "classes": ["unicorn"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_agent_skips_vista_when_overlay_already_matches():
    dicom = MemoryDicom()
    dicom.ct_files["ct-study-1"] = [b"CT0"]
    app, deps, _audit = _app(dicom=dicom)
    deps.clinical.report_rows.append(
        {
            "source_id": "seed-demo/DiagnosticReport/p102-ct-2026-07-01-vista",
            "patient_key": "p_102",
            "conclusion_text": "VISTA-3D overlay on CT: heart. Toggle the segmentation in the study viewer.",
        }
    )
    with patch("patient360.reprocess.vista_segment") as segment:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/auth/dev-login", json={"login": "chen", "on_duty": True, "auth_level": 2})
            token = (await client.post("/dev/run-token", json={})).json()["access_token"]
            r = await client.post(
                "/tools/imaging",
                json={"patient_key": "p_102", "classes": ["heart"]},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert r.status_code == 200, r.text
    assert r.json()["overlay_classes"] == ["heart"]
    assert "heart" in r.json()["allowed_classes"]
    segment.assert_not_called()
    assert dicom.stored == []


@pytest.mark.asyncio
async def test_rivera_cannot_prompt_vista():
    app, *_ = _app(dicom=MemoryDicom())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/dev-login", json={"login": "rivera", "on_duty": True, "auth_level": 2})
        token = (await client.post("/dev/run-token", json={})).json()["access_token"]
        r = await client.post(
            "/tools/imaging",
            json={"patient_key": "p_102", "study_id": "ct-study-1", "classes": ["heart"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404
