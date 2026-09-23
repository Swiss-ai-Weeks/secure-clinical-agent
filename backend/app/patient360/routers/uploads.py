"""Dashboard uploads: quarantine, sanitize, publish as chart notes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent
from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..deid import IdentityHints, chunk_text, sanitize
from ..errors import Deny, NotFound
from ..nemo_rails import rails_for
from ..pdf_text import extract_pdf_text, looks_like_pdf
from ..pdp import Context, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE

router = APIRouter(tags=["uploads"])


class DeleteUpload(BaseModel):
    patient_key: str
    document_id: str


def upload_provenance(role: str) -> str:
    """A patient upload is patient-reported. A clinician upload is a clinical note."""
    return "patient-reported" if role == "patient" else "clinical"


def upload_object_key(patient_key: str, document_id: str) -> str:
    key = (document_id or "").strip()
    prefix = f"notes/{patient_key}/"
    name = key[len(prefix) :] if key.startswith(prefix) else ""
    if not name or "/" in name or ".." in name:
        raise NotFound()
    return key


def upload_text(raw: bytes, filename: str, content_type: str) -> str | None:
    """Text the chart may publish. PDFs are extracted; other binaries stay out."""
    if looks_like_pdf(raw, filename, content_type):
        text = extract_pdf_text(raw)
        return text or None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


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

    text = upload_text(raw, file.filename or "", file.content_type or "")
    if text is None:
        return {"documentId": key, "status": "quarantine", "reason": "not_text"}

    result = sanitize(text, IdentityHints())
    if not result.ok:
        return {"documentId": key, "status": "quarantine", "reason": "canary"}

    rail = await rails_for(deps).check_document(result.text)
    if not rail.ok:
        return {"documentId": key, "status": "quarantine", "reason": rail.reason}

    sanitized_key = f"notes/{patient_key}/{file.filename or 'upload'}.txt"
    provenance = upload_provenance(caller.subject.role)
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
                    "provenance": provenance,
                    "source": "upload",
                    "uploader_role": caller.subject.role,
                    "type_display": file.filename or "upload",
                    "authored_at": now.isoformat(),
                    "sanitized_ref": sanitized_key,
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
            "provenance": provenance,
            "source": "upload",
            "uploader_role": caller.subject.role,
            "text": result.text,
        }
    ) if hasattr(deps.clinical, "note_rows") else None
    return {"documentId": sanitized_key, "status": "processed", "provenance": provenance}


@router.delete("/uploads")
async def delete_upload(body: DeleteUpload, caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    now = utcnow()
    key = upload_object_key(body.patient_key, body.document_id)
    resource = Resource(type="notes", patient_key=body.patient_key)
    decision = await evaluate(
        caller.subject,
        resource,
        Context(now=now, channel="dashboard", purpose=PURPOSE_BY_ROLE.get(caller.subject.role, "PATRQT")),
        deps.fga.check,
    )
    await deps.audit.write(
        AuditEvent(
            event_type="upload",
            agent_user=caller.user.user_id,
            purpose_of_event="PATRQT",
            entity_patient=body.patient_key,
            entity_resource=key,
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            outcome_desc="deleted",
            reason_code=decision.reason_code,
            session_id=caller.sid,
        )
    )
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)

    filename = key.rsplit("/", 1)[-1]
    if filename.endswith(".txt"):
        filename = filename[:-4]
    await deps.notes.delete_note(body.patient_key, key)
    await deps.objects.delete("reports", key)
    await deps.objects.delete("quarantine", f"quarantine/{body.patient_key}/{filename}")
    if hasattr(deps.clinical, "note_rows"):
        deps.clinical.note_rows[:] = [  # type: ignore[attr-defined]
            row
            for row in deps.clinical.note_rows  # type: ignore[attr-defined]
            if row.get("note_id") != key and row.get("cite_id") != key
        ]
    return {"documentId": key, "status": "deleted"}
