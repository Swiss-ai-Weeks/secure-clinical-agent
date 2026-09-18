"""POST /tools/imaging: report text or metadata. Never pixels."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from ..errors import Deny, NotFound
from ..pdp import Context, Decision, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE
from ..pdp.relations import BREAK_GLASS_ROLES
from .query import _agent_software
from .schemas import DecisionOut, ImagingRequest, ImagingResponse

if TYPE_CHECKING:
    from ..auth.subject import Caller
    from ..deps import AppDeps


async def run_imaging(
    deps: AppDeps, caller: Caller, req: ImagingRequest, *, now: datetime
) -> ImagingResponse:
    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    raw = req.model_dump(mode="json")
    resource = Resource(type="imaging_report", patient_key=req.patient_key)
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

    decision.audit_id = await deps.audit.write(
        AuditEvent(
            event_type="decision",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource="imaging_report",
            entity_query=encode_query(raw),
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            outcome_desc=decision.effect,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            reason_code=decision.reason_code,
            session_id=caller.sid,
            jti=caller.jti,
            detail={
                "channel": caller.channel,
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

    studies, reports = await deps.clinical.list_imaging(req.patient_key)
    if decision.obligations.imaging_tier == "metadata":
        reports = [
            {
                k: v
                for k, v in row.items()
                if k
                not in {
                    "conclusion_text",
                    "report_ref",
                }
            }
            | {"tier": "metadata"}
            for row in reports
        ]
    await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource="imaging_report",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="imaging_returned",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            jti=caller.jti,
            detail={"decision_audit_id": str(decision.audit_id), "studies": len(studies)},
        )
    )
    return ImagingResponse(
        patient_key=req.patient_key,
        studies=studies,
        reports=reports,
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
