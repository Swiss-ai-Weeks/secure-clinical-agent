"""POST /tools/notes: PDP first, then a server-built Qdrant filter."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from ..errors import Deny, NotFound
from ..pdp import Context, Decision, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE
from ..pdp.relations import BREAK_GLASS_ROLES
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
    by_note = {str(c.get("note_id")): c.get("text") for c in chunks if c.get("note_id")}
    for note in notes:
        if not note.get("text"):
            note["text"] = by_note.get(str(note.get("note_id") or "")) or by_note.get(
                str(note.get("source_id") or "")
            )

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
