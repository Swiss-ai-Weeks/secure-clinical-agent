"""POST /tools/imaging: report text or metadata. Never pixels.

Optional `classes` runs VISTA-3D on a CT (same PDP as dashboard reprocess) and
stores a SEG. The tool still returns text only.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from ..errors import Deny, Invalid, NotFound
from ..pdp import Context, Decision, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE
from ..pdp.relations import BREAK_GLASS_ROLES
from ..reprocess import ReprocessRequest, reprocess_ct
from ..vista_overlay import ALLOWED_CLASSES, normalize_classes
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
    overlay: dict[str, Any] | None = None
    if req.classes is not None:
        try:
            classes = normalize_classes(req.classes)
        except ValueError as exc:
            raise Invalid("vista_class_unknown", str(exc)) from exc
        study_id = req.study_id or _sole_ct_study(studies)
        if not study_id:
            raise Invalid("vista_study_required", "Name the CT study to segment")
        if _overlay_already_stored(reports, classes):
            overlay = {
                "classes": list(classes),
                "report_text": next(
                    str(row.get("conclusion_text") or "")
                    for row in reports
                    if "vista-3d" in str(row.get("conclusion_text") or "").lower()
                ),
                "study_id": study_id,
            }
        else:
            overlay = await reprocess_ct(
                deps,
                caller,
                ReprocessRequest(patient_key=req.patient_key, study_id=study_id, classes=classes),
                now=now,
            )
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
        studies=_tool_rows(studies),
        reports=_tool_rows(reports),
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
        overlay_classes=list(overlay["classes"]) if overlay else None,
        overlay_text=str(overlay["report_text"]) if overlay else None,
        overlay_study_id=str(overlay["study_id"]) if overlay else None,
        allowed_classes=sorted(ALLOWED_CLASSES),
    )


def _overlay_already_stored(reports: list[dict[str, Any]], classes: tuple[str, ...]) -> bool:
    for row in reports:
        text = str(row.get("conclusion_text") or "").lower()
        if "vista-3d" in text and all(name in text for name in classes):
            return True
    return False


def _tool_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key != "resource"} for row in rows]


def _sole_ct_study(studies: list[dict[str, Any]]) -> str | None:
    cts = [
        str(row.get("orthanc_id") or "")
        for row in studies
        if str(row.get("modality") or "").upper() == "CT" and row.get("orthanc_id")
    ]
    if len(cts) == 1:
        return cts[0]
    return None
