"""identity_banner (Build Plan §4.5): the PDP-checked read that puts a name on the dashboard.

Dashboard channel only. Self, or a live clinical relationship for a banner role
(attending, care_team, consultant, caregiver). Returns the banner projection of the
vault record and nothing else; a missing vault record is the uniform not-found.
A read under a live break-glass activation is labelled BTG like any other read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from .errors import Deny, NotFound
from .pdp import Context, Resource, evaluate
from .pdp.models import PURPOSE_BY_ROLE
from .pdp.relations import BREAK_GLASS_ROLES

if TYPE_CHECKING:
    from .auth.subject import Caller
    from .deps import AppDeps


@dataclass(slots=True)
class BannerResult:
    banner: dict[str, Any]
    audit_id: UUID
    identity_audit_id: UUID
    purpose_of_event: str
    compliance_flag: bool


async def identity_banner(deps: AppDeps, caller: Caller, patient_key: str, *, now: datetime) -> BannerResult:
    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    resource = Resource(type="identity", patient_key=patient_key)
    context = Context(now=now, channel=caller.channel, purpose=purpose, action="read")
    decision = await evaluate(subject, resource, context, deps.fga.check)

    detail: dict[str, Any] = {
        "channel": caller.channel,
        "relation": decision.relation,
        "fga_consulted": decision.fga_consulted,
        "operation": "identity_banner",
    }
    if decision.permitted and decision.fga_consulted and subject.role in BREAK_GLASS_ROLES:
        activation = await deps.audit_reader.active_break_glass(subject.user_id, patient_key, now)
        if activation is not None:
            purpose = "BTG"
            decision.compliance_flag = True
            detail["break_glass_audit_id"] = str(activation["id"])
    detail["compliance_flag"] = decision.compliance_flag

    decision.audit_id = await deps.audit.write(
        AuditEvent(
            event_type="decision",
            agent_user=subject.user_id,
            purpose_of_event=purpose,
            entity_patient=patient_key,
            entity_resource="identity/banner",
            entity_query=encode_query({"patient_key": patient_key}),
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            outcome_desc=decision.effect,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            reason_code=decision.reason_code,
            session_id=caller.sid,
            detail=detail,
        )
    )
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)
    assert decision.audit_id is not None

    identity = await deps.vault.read_identity(patient_key)
    identity_audit_id = await deps.audit.write(
        AuditEvent(
            event_type="identity_resolve",
            agent_user=subject.user_id,
            purpose_of_event=purpose,
            entity_patient=patient_key,
            entity_resource="vault/identity",
            outcome=OUTCOME_SUCCESS if identity is not None else OUTCOME_MINOR,
            outcome_desc="vault.identity_banner",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            detail={
                "operation": "identity_banner",
                "resolved": identity is not None,
                "decision_audit_id": str(decision.audit_id),
            },
        )
    )
    if identity is None:
        raise NotFound()
    return BannerResult(
        banner=identity.banner(),
        audit_id=decision.audit_id,
        identity_audit_id=identity_audit_id,
        purpose_of_event=purpose,
        compliance_flag=decision.compliance_flag,
    )


async def visible_patient_keys(deps: AppDeps, caller: Caller, *, now: datetime) -> list[str]:
    """Patient keys this dashboard caller may open: self plus a live clinical grant."""
    keys: set[str] = set()
    if caller.session.self_patient_id:
        keys.add(caller.session.self_patient_id)
    permission = "can_read_diet" if caller.user.role == "dietary_staff" else "can_read_clinical"
    try:
        objects = await deps.fga.list_objects(
            f"user:{caller.user.user_id}", permission, "patient", now
        )
    except Exception:
        objects = []
    for obj in objects:
        _, _, key = obj.partition(":")
        if key.startswith("p_"):
            keys.add(key)
    return sorted(keys)
