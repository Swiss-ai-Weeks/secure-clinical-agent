"""Appointment book / cancel (Build Plan §5.2). Dashboard channel, session cookie."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from .audit import AuditEvent, encode_query
from .auth.sessions import PRACTITIONER_ROLES
from .errors import Conflict, Invalid, NotFound
from .humanwrites import _decision_row, _raise_for
from .pdp import Context, Resource, evaluate
from .pdp.models import PURPOSE_BY_ROLE

if TYPE_CHECKING:
    from .auth.subject import Caller
    from .deps import AppDeps


@dataclass(slots=True)
class BookRequest:
    patient_key: str
    practitioner_user_id: str
    start: datetime
    end: datetime | None = None
    dept: str | None = None
    service_type: str | None = None
    service_type_system: str | None = None
    service_type_display: str | None = None


async def book_appointment(
    deps: AppDeps, caller: Caller, req: BookRequest, *, now: datetime
) -> dict[str, Any]:
    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    practitioner = await deps.users.get(req.practitioner_user_id)
    if practitioner is None or not practitioner.active or practitioner.role not in PRACTITIONER_ROLES:
        raise Invalid("practitioner_invalid", "Practitioner is not an active care-role user")
    if req.end is not None and req.end <= req.start:
        raise Invalid("expiry_before_start", "end must be after start")

    resource = Resource(type="clinical_rows", patient_key=req.patient_key, dataset="encounters")
    context = Context(now=now, channel=caller.channel, purpose=purpose, action="schedule")
    decision = await evaluate(subject, resource, context, deps.fga.check)
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=req.patient_key,
        resource="appointment",
        query=asdict(req),
        extra={"action": "schedule"},
    )
    _raise_for(decision)
    assert decision.audit_id is not None

    row = await deps.clinical.insert_appointment(
        {
            "source_id": f"Appointment/{uuid4().hex}",
            "patient_key": req.patient_key,
            "practitioner_user_id": req.practitioner_user_id,
            "status": "booked",
            "start_at": req.start,
            "end_at": req.end,
            "dept": req.dept or practitioner.department,
            "service_type": req.service_type,
            "service_type_system": req.service_type_system,
            "service_type_display": req.service_type_display,
            "created_by": subject.user_id,
        }
    )
    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="appointment_booked",
            agent_user=subject.user_id,
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource=f"appointment/{row['id']}",
            entity_query=encode_query({"patient_key": req.patient_key}),
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            detail={"appointment_id": str(row["id"]), "decision_audit_id": str(decision.audit_id)},
        )
    )
    return {**_public(row), "audit_id": str(audit_id), "decision_audit_id": str(decision.audit_id)}


async def cancel_appointment(
    deps: AppDeps, caller: Caller, appointment_id: UUID, *, now: datetime
) -> dict[str, Any]:
    row = await deps.clinical.get_appointment(appointment_id)
    if row is None:
        raise NotFound()
    if row.get("status") == "cancelled":
        raise Conflict("already_cancelled")

    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    resource = Resource(type="clinical_rows", patient_key=row["patient_key"], dataset="encounters")
    context = Context(
        now=now,
        channel=caller.channel,
        purpose=purpose,
        action="cancel",
        appointment_created_by=row.get("created_by"),
        appointment_practitioner=row.get("practitioner_user_id"),
    )
    decision = await evaluate(subject, resource, context, deps.fga.check)
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=row["patient_key"],
        resource="appointment",
        query={"appointment_id": str(appointment_id)},
        extra={"action": "cancel"},
    )
    _raise_for(decision)
    updated = await deps.clinical.update_appointment(appointment_id, {"status": "cancelled"})
    assert updated is not None
    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="appointment_cancelled",
            agent_user=subject.user_id,
            purpose_of_event=purpose,
            entity_patient=row["patient_key"],
            entity_resource=f"appointment/{appointment_id}",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            detail={"appointment_id": str(appointment_id), "decision_audit_id": str(decision.audit_id)},
        )
    )
    return {**_public(updated), "audit_id": str(audit_id), "decision_audit_id": str(decision.audit_id)}


async def availability(
    deps: AppDeps,
    *,
    now: datetime,
    department: str | None = None,
    practitioner_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Free 30-minute slots over the next 14 days. Opaque practitioner ids, no names."""
    care = await deps.users.list_care()
    if department:
        care = [u for u in care if u.department == department]
    if practitioner_user_id:
        care = [u for u in care if u.user_id == practitioner_user_id]
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end = start + timedelta(days=14)
    booked = await deps.clinical.booked_windows(
        practitioner_user_id=practitioner_user_id, start=start, end=end
    )
    taken = {(b["practitioner_user_id"], _slot_key(b["start_at"])) for b in booked}
    slots: list[dict[str, Any]] = []
    for user in care:
        day = start
        while day < end:
            if day.weekday() < 5:
                for hour in (9, 14):
                    slot_start = day.replace(hour=hour)
                    if (user.user_id, _slot_key(slot_start)) in taken:
                        continue
                    slots.append(
                        {
                            "practitioner_user_id": user.user_id,
                            "department": user.department,
                            "start": slot_start,
                            "end": slot_start + timedelta(minutes=30),
                        }
                    )
            day += timedelta(days=1)
    return slots


def _slot_key(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "cite_id": row.get("cite_id"),
        "patient_key": row["patient_key"],
        "practitioner_user_id": row["practitioner_user_id"],
        "status": row["status"],
        "start": row.get("start_at") or row.get("start"),
        "end": row.get("end_at") or row.get("end"),
        "dept": row.get("dept"),
        "service_type_display": row.get("service_type_display"),
        "created_by": row.get("created_by"),
    }
