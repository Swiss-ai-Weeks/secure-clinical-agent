"""Dashboard CT reprocess: session cookie, PDP on pixels, VISTA-3D → SEG."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from psycopg.types.json import Jsonb

from .audit import OUTCOME_SUCCESS, AuditEvent
from .dicom import _safe_id
from .errors import Invalid, NotFound, Transient
from .humanwrites import _decision_row, _raise_for
from .pdp import Context, Resource, evaluate
from .pdp.models import PURPOSE_BY_ROLE
from .vista_overlay import (
    build_overlay,
    normalize_classes,
    study_key_from_source,
    vista_report_source,
)

if TYPE_CHECKING:
    from .auth.subject import Caller
    from .deps import AppDeps

log = logging.getLogger(__name__)
REPROCESS_ROLES = frozenset({"attending", "consultant"})
LOINC = "http://loinc.org"


@dataclass(slots=True)
class ReprocessRequest:
    patient_key: str
    study_id: str
    classes: tuple[str, ...] | None = None


def _json_request(url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> tuple[int, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/octet-stream, application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.getcode() or 200, resp.read()
    except HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        return exc.code, raw
    except URLError as exc:
        raise Transient("vista unavailable") from exc


def vista_segment(url: str, image_path: str, classes: tuple[str, ...], *, timeout: float) -> bytes:
    payload: dict[str, Any] = {"image": image_path}
    if classes:
        payload["prompts"] = {"classes": list(classes)}
    code, raw = _json_request(f"{url.rstrip('/')}/v1/vista3d/inference", payload, timeout=timeout)
    if code != 200 or not raw:
        log.error("vista inference failed: http=%s bytes=%s", code, len(raw))
        raise Transient("vista unavailable")
    return raw


async def reprocess_ct(
    deps: AppDeps, caller: Caller, req: ReprocessRequest, *, now: datetime
) -> dict[str, Any]:
    if not _safe_id(req.study_id):
        raise NotFound()
    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    resource = Resource(type="imaging_pixels", patient_key=req.patient_key)
    context = Context(now=now, channel=caller.channel, purpose=purpose, action="read")
    decision = await evaluate(subject, resource, context, deps.fga.check)
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=req.patient_key,
        resource="imaging_pixels",
        query={"study_id": req.study_id, "classes": list(req.classes or ())},
        extra={"action": "reprocess"},
    )
    _raise_for(decision)
    if subject.role not in REPROCESS_ROLES:
        raise NotFound()
    study = await deps.clinical.get_study(req.patient_key, req.study_id)
    if study is None:
        raise NotFound()
    if str(study.get("modality") or "").upper() != "CT":
        raise Invalid("vista_not_ct", "VISTA-3D only runs on CT")
    if deps.dicom is None:
        raise Transient("vista unavailable")
    if not deps.settings.vista_url:
        raise Transient("vista unavailable")

    try:
        classes = normalize_classes(req.classes, default=("heart",))
    except ValueError as exc:
        raise Invalid("vista_class_unknown", str(exc)) from exc

    work = Path(deps.settings.vista_work_dir) / "work" / req.study_id
    try:
        source_files = await deps.dicom.export_ct(req.study_id, work)
    except Exception as exc:
        log.error("vista export failed: %s", exc.__class__.__name__)
        raise Transient("vista unavailable") from exc
    if not source_files:
        raise NotFound()

    image_path = f"/data/patient360/work/{req.study_id}"
    try:
        mask = vista_segment(
            deps.settings.vista_url,
            image_path,
            classes,
            timeout=deps.settings.vista_timeout_seconds,
        )
        overlay = build_overlay(
            mask,
            source_files,
            classes=classes,
            study_key=study_key_from_source(str(study.get("source_id") or req.study_id)),
        )
        await deps.dicom.delete_vista_seg(req.study_id)
        await deps.dicom.store_instance(overlay.seg_bytes)
    except Transient:
        raise
    except Exception as exc:
        log.error("vista overlay persist failed: %s", exc.__class__.__name__)
        raise Transient("vista unavailable") from exc

    report = await deps.clinical.upsert_vista_report(
        {
            "source_id": vista_report_source(str(study.get("source_id") or req.study_id)),
            "patient_key": req.patient_key,
            "encounter_id": study.get("encounter_id"),
            "status": "final",
            "category": "CT",
            "code": study.get("procedure_code") or "24627-2",
            "code_system": LOINC,
            "display": f"{study.get('procedure_display') or 'CT'} VISTA-3D overlay",
            "effective_at": study.get("study_at") or now,
            "issued_at": now.astimezone(UTC),
            "conclusion_text": overlay.report_text,
            "study_id": study.get("id"),
            "confidentiality": "N",
            "sensitivity": [],
            "resource": Jsonb({"resourceType": "DiagnosticReport", "status": "final"}),
        }
    )
    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="vista_reprocess",
            agent_user=subject.user_id,
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource=req.study_id,
            outcome=OUTCOME_SUCCESS,
            outcome_desc="vista_overlay_stored",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            detail={
                "decision_audit_id": str(decision.audit_id),
                "classes": list(overlay.classes),
                "series_uid": overlay.series_uid,
            },
        )
    )
    return {
        "patient_key": req.patient_key,
        "study_id": req.study_id,
        "classes": list(overlay.classes),
        "report_text": overlay.report_text,
        "series_uid": overlay.series_uid,
        "report_source_id": report.get("source_id"),
        "audit_id": str(audit_id),
        "decision_audit_id": str(decision.audit_id),
    }
