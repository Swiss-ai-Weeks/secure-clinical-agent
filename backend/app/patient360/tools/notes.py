"""POST /tools/notes: PDP first, then a server-built Qdrant filter."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from ..clinical_view import clean_synthea_note
from ..errors import Deny, NotFound
from ..pdp import Context, Decision, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE
from ..pdp.relations import BREAK_GLASS_ROLES, PIXEL_ROLES
from ..publication import chunk_visible
from .query import _agent_software
from .schemas import DecisionOut, NotesRequest, NotesResponse

if TYPE_CHECKING:
    from ..auth.subject import Caller
    from ..deps import AppDeps


def allowed_confidentiality(redact: dict[str, str]) -> tuple[str, ...] | None:
    """Drop labels the obligations redact. None means every label is allowed."""
    blocked = frozenset(redact)
    if not blocked:
        return None
    return tuple(label for label in ("N", "R", "V") if label not in blocked)


def _without_signed_file(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the stored-file pointer when this role cannot open signed bytes."""
    if "sanitized_ref" not in row:
        return row
    return {key: value for key, value in row.items() if key != "sanitized_ref"}


def _chart_upload(card: dict[str, Any]) -> bool:
    if card.get("source") == "upload" or card.get("provenance") == "patient-reported":
        return True
    return str(card.get("note_id") or "").startswith("notes/")


def notes_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build note cards from Qdrant hits when clinical.notes has no published row."""
    grouped: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        note_id = str(chunk.get("note_id") or chunk.get("cite_id") or "")
        if not note_id:
            continue
        piece = str(chunk.get("text") or "").strip()
        current = grouped.get(note_id)
        if current is None:
            patient_key = str(chunk.get("patient_key") or "")
            prefix = f"{patient_key}-"
            alias = note_id[len(prefix) :] if patient_key and note_id.startswith(prefix) else ""
            filename = note_id.rsplit("/", 1)[-1]
            if filename.endswith(".txt"):
                filename = filename[:-4]
            title = str(chunk.get("type_display") or "").strip() or (
                filename if note_id.startswith("notes/") and filename else ""
            ) or (alias.replace("-", " ").strip().capitalize() if alias else "Clinical note")
            ref = chunk.get("sanitized_ref") or (note_id if note_id.startswith("notes/") else None)
            grouped[note_id] = {
                "note_id": note_id,
                "cite_id": chunk.get("cite_id") or note_id,
                "type_display": title,
                "authored_at": chunk.get("authored_at"),
                "provenance": chunk.get("provenance") or "clinical",
                "source": chunk.get("source"),
                "uploader_role": chunk.get("uploader_role"),
                "published": True,
                "sanitized_ref": ref,
                "text": piece,
                "redacted": bool(chunk.get("redacted")),
            }
            continue
        if piece and piece not in (current.get("text") or ""):
            current["text"] = f"{current['text']}\n\n{piece}" if current.get("text") else piece
    return list(grouped.values())


async def run_notes(deps: AppDeps, caller: Caller, req: NotesRequest, *, now: datetime) -> NotesResponse:
    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    raw = req.model_dump(mode="json")
    detail_base: dict[str, Any] = {"channel": caller.channel}
    if req.ignored_args():
        detail_base["ignored_args"] = req.ignored_args()

    patient_age: int | None = None
    if subject.role == "caregiver":
        birth_year = await deps.clinical.patient_birth_year(req.patient_key)
        patient_age = now.year - birth_year if birth_year is not None else None

    resource = Resource(type="notes", patient_key=req.patient_key, patient_age=patient_age)
    context = Context(
        now=now,
        channel=caller.channel,
        purpose=purpose,
        action="read",
        jti=caller.jti,
        adolescent_age=deps.settings.adolescent_age,
        majority_age=deps.settings.majority_age,
    )
    decision: Decision = await evaluate(subject, resource, context, deps.fga.check)
    if decision.permitted and decision.fga_consulted and subject.role in BREAK_GLASS_ROLES:
        activation = await deps.audit_reader.active_break_glass(subject.user_id, req.patient_key, now)
        if activation is not None:
            purpose = "BTG"
            decision.compliance_flag = True
            detail_base["break_glass_audit_id"] = str(activation["id"])

    decision.audit_id = await deps.audit.write(
        AuditEvent(
            event_type="decision",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource="notes",
            entity_query=encode_query(raw),
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            outcome_desc=decision.effect,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            reason_code=decision.reason_code,
            session_id=caller.sid,
            jti=caller.jti,
            detail={
                **detail_base,
                "relation": decision.relation,
                "fga_consulted": decision.fga_consulted,
                "obligations": decision.obligations.as_dict(),
            },
        )
    )
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)
    assert decision.audit_id is not None

    conf = allowed_confidentiality(decision.obligations.redact)
    chunks = await deps.notes.search(
        req.question or "clinical notes",
        patient_key=req.patient_key,
        published=True,
        allowed_confidentiality=conf,
        exclude_internal=decision.obligations.exclude_internal,
    )
    notes = await deps.clinical.list_notes(req.patient_key)
    if decision.obligations.exclude_internal:
        notes = [n for n in notes if not n.get("internal")]
    if conf is not None:
        notes = [n for n in notes if n.get("confidentiality") in conf]
        notes = [
            (
                {**n, "redacted": True, "text": None}
                if n.get("confidentiality") in decision.obligations.redact
                else n
            )
            for n in notes
        ]
    chunks = [c for c in chunks if chunk_visible(c)]
    notes = [n for n in notes if chunk_visible(n)]
    by_note = {str(c.get("note_id")): c.get("text") for c in chunks if c.get("note_id")}
    titles = {
        str(note.get("note_id") or note.get("source_id") or ""): note.get("type_display")
        for note in notes
        if note.get("type_display")
    }
    for note in notes:
        source = str(note.get("source_id") or "")
        if not note.get("note_id") and source:
            note["note_id"] = source.rsplit("/", 1)[-1]
        if not note.get("text"):
            note["text"] = by_note.get(str(note.get("note_id") or "")) or by_note.get(source)
    for chunk in chunks:
        if not chunk.get("type_display"):
            title = titles.get(str(chunk.get("note_id") or "")) or titles.get(str(chunk.get("cite_id") or ""))
            if title:
                chunk["type_display"] = title
    if not notes and chunks:
        notes = notes_from_chunks(chunks)
    else:
        known = {
            str(note.get(key) or "")
            for note in notes
            for key in ("note_id", "cite_id", "source_id", "sanitized_ref")
            if note.get(key)
        }
        uploaded = [
            card
            for card in notes_from_chunks(chunks)
            if _chart_upload(card)
            and str(card.get("note_id") or "") not in known
            and str(card.get("cite_id") or "") not in known
        ]
        notes = uploaded + notes
    for note in notes:
        if note.get("text") and not note.get("redacted"):
            note["text"] = clean_synthea_note(str(note["text"]))
    for chunk in chunks:
        if chunk.get("text") and not chunk.get("redacted"):
            chunk["text"] = clean_synthea_note(str(chunk["text"]))
    if subject.role not in PIXEL_ROLES:
        notes = [_without_signed_file(note) for note in notes]
        chunks = [_without_signed_file(chunk) for chunk in chunks]

    await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource="notes",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="notes_returned",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            jti=caller.jti,
            detail={"decision_audit_id": str(decision.audit_id), "chunks": len(chunks), "notes": len(notes)},
        )
    )
    return NotesResponse(
        patient_key=req.patient_key,
        chunks=chunks,
        notes=notes,
        chunk_count=len(chunks),
        obligations=decision.obligations.as_dict(),
        decision=DecisionOut(
            effect=decision.effect,
            reason_code=decision.reason_code,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            relation=decision.relation,
            purpose_of_event=purpose,
            compliance_flag=decision.compliance_flag,
        ),
        audit_id=decision.audit_id,
    )
