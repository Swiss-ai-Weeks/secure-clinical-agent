"""Dashboard uploads: quarantine, sanitize, publish as patient-reported notes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent
from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..deid import IdentityHints, chunk_text, sanitize
from ..errors import Deny, NotFound
from ..pdp import Context, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE

router = APIRouter(tags=["uploads"])


@router.post("/uploads")
async def upload_document(
    caller: SessionCallerDep,
    deps: DepsDep,
    patient_key: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    now = utcnow()
    resource = Resource(type="notes", patient_key=patient_key)
    decision = await evaluate(
        caller.subject,
        resource,
        Context(now=now, channel="dashboard", purpose=PURPOSE_BY_ROLE.get(caller.subject.role, "PATRQT")),
        deps.fga.check,
    )
    raw = await file.read()
    key = f"quarantine/{patient_key}/{file.filename or 'upload.bin'}"
    await deps.objects.put(
        "quarantine", key, raw, content_type=file.content_type or "application/octet-stream"
    )
    await deps.audit.write(
        AuditEvent(
            event_type="upload",
            agent_user=caller.user.user_id,
            purpose_of_event="PATRQT",
            entity_patient=patient_key,
            entity_resource=key,
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            reason_code=decision.reason_code,
            session_id=caller.sid,
        )
    )
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"documentId": key, "status": "quarantine", "reason": "not_text"}

    result = sanitize(text, IdentityHints())
    if not result.ok:
        return {"documentId": key, "status": "quarantine", "reason": "canary"}

    sanitized_key = f"notes/{patient_key}/{file.filename or 'upload'}.txt"
    await deps.objects.put("reports", sanitized_key, result.text.encode(), content_type="text/plain")
    chunks = chunk_text(result.text, sanitized_key)
    await deps.notes.upsert(
        [
            {
                "id": c.point_id,
                "payload": {
                    "patient_key": patient_key,
                    "note_id": sanitized_key,
                    "cite_id": c.point_id[:8],
                    "confidentiality": "N",
                    "published": True,
                    "internal": False,
                    "provenance": "patient-reported",
                    "text": c.text,
                    "deid_version": result.deid_version,
                },
            }
            for c in chunks
        ]
    )
    deps.clinical.note_rows.append(  # type: ignore[attr-defined]
        {
            "cite_id": sanitized_key,
            "note_id": sanitized_key,
            "patient_key": patient_key,
            "type_display": file.filename or "upload",
            "authored_at": now.isoformat(),
            "internal": False,
            "published": True,
            "confidentiality": "N",
            "provenance": "patient-reported",
            "text": result.text,
        }
    ) if hasattr(deps.clinical, "note_rows") else None
    return {"documentId": sanitized_key, "status": "processed"}
