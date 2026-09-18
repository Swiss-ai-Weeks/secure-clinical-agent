"""POST /tools/query: per-patient clinical rows behind the PDP.

Flow: resolve caller -> PDP decision -> decision audit row -> not_found / deny
-> read `WHERE patient_key = decision's key` -> apply REDACT row-wise ->
tool_call audit row -> response with the decision audit id.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from ..errors import Deny, NotFound
from ..pdp import Context, Decision, Obligations, Resource, evaluate
from ..pdp.models import PURPOSE_BY_ROLE
from ..pdp.relations import AGGREGATE_DIMS, BREAK_GLASS_ROLES
from .aggregate import apply_suppression, filter_equalities, overlaps_prior
from .schemas import DecisionOut, QueryRequest, QueryResponse

if TYPE_CHECKING:
    from ..auth.subject import Caller
    from ..deps import AppDeps

log = logging.getLogger(__name__)

REDACTED_KEEP = ("cite_id", "confidentiality")


def apply_redaction(rows: list[dict[str, Any]], obligations: Obligations) -> tuple[list[dict[str, Any]], int]:
    """Rows whose confidentiality is in the obligations keep only cite_id and the label."""
    if not obligations.redact:
        return rows, 0
    out: list[dict[str, Any]] = []
    redacted = 0
    for row in rows:
        label = row.get("confidentiality", "N")
        reason = obligations.redact.get(label)
        if reason is None:
            out.append(row)
            continue
        redacted += 1
        out.append({**{k: row.get(k) for k in REDACTED_KEEP}, "redacted": True, "redact_reason": reason})
    return out, redacted


def _agent_software(caller: Caller, deps: AppDeps) -> str:
    return caller.agent if caller.channel == "agent" and caller.agent else deps.settings.agent_software


async def run_query(deps: AppDeps, caller: Caller, req: QueryRequest, *, now: datetime) -> QueryResponse:
    subject = caller.subject
    purpose = PURPOSE_BY_ROLE.get(subject.role, "HOPERAT")
    raw = req.model_dump(mode="json")
    detail_base: dict[str, Any] = {"channel": caller.channel}
    if req.ignored_args():
        detail_base["ignored_args"] = req.ignored_args()
        if req.ignored_identity_args():
            detail_base["ignored_identity_args"] = req.ignored_identity_args()

    if req.aggregate is not None:
        return await _run_aggregate(
            deps, caller, req, now=now, purpose=purpose, raw=raw, detail_base=detail_base
        )

    if not req.patient_key:
        raise NotFound()

    # Age feeds the adolescent-confidentiality obligation for caregiver-role readers. It is
    # resolved before the decision and only ever narrows a permit; an unknown patient yields
    # None and is the uniform not-found regardless.
    patient_age: int | None = None
    if subject.role == "caregiver":
        birth_year = await deps.clinical.patient_birth_year(req.patient_key)
        patient_age = now.year - birth_year if birth_year is not None else None

    resource = Resource(
        type="clinical_rows", patient_key=req.patient_key, dataset=req.dataset, patient_age=patient_age
    )
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

    # A permit that rides on a live break-glass activation is labelled BTG (Build Plan §2,
    # §4.2). The activation is read from the audit log, the provenance record, so the PDP
    # keeps checking permissions and never the raw emergency relation.
    if decision.permitted and decision.fga_consulted and subject.role in BREAK_GLASS_ROLES:
        activation = await deps.audit_reader.active_break_glass(subject.user_id, req.patient_key, now)
        if activation is not None:
            purpose = "BTG"
            decision.compliance_flag = True
            detail_base["break_glass_audit_id"] = str(activation["id"])
            detail_base["break_glass_expiry"] = (activation.get("detail") or {}).get("expiry")

    decision.audit_id = await deps.audit.write(
        AuditEvent(
            event_type="decision",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource=f"clinical_rows/{req.dataset}",
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
                "compliance_flag": decision.compliance_flag,
                **({"patient_age": patient_age} if patient_age is not None else {}),
            },
        )
    )

    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)

    rows = await deps.clinical.fetch(req.dataset, req.patient_key, req.filters, decision.obligations)
    rows, redacted = apply_redaction(rows, decision.obligations)

    await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=req.patient_key,
            entity_resource=f"clinical_rows/{req.dataset}",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="rows_returned",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            jti=caller.jti,
            detail={"decision_audit_id": str(decision.audit_id), "rows": len(rows), "redacted": redacted},
        )
    )

    assert decision.audit_id is not None
    return QueryResponse(
        patient_key=req.patient_key,
        dataset=req.dataset,
        rows=rows,
        row_count=len(rows),
        redacted_count=redacted,
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


async def _run_aggregate(
    deps: AppDeps,
    caller: Caller,
    req: QueryRequest,
    *,
    now: datetime,
    purpose: str,
    raw: dict[str, Any],
    detail_base: dict[str, Any],
) -> QueryResponse:
    subject = caller.subject
    spec = req.aggregate
    assert spec is not None
    group_by = list(spec.group_by)
    allowed = tuple(sorted(AGGREGATE_DIMS.get(req.dataset, frozenset())))
    resource = Resource(type="aggregate", dataset=req.dataset)
    context = Context(
        now=now,
        channel=caller.channel,
        purpose=purpose,
        action="read",
        jti=caller.jti,
        group_by=tuple(group_by),
        project_id=spec.project_id,
        k_min=deps.settings.effective_k_min,
        allowed_dims=allowed,
    )
    decision: Decision = await evaluate(
        subject, resource, context, deps.fga.check, list_objects=deps.fga.list_objects
    )

    decision.audit_id = await deps.audit.write(
        AuditEvent(
            event_type="decision",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_patient=None,
            entity_resource=f"aggregate/{req.dataset}",
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
                "project_id": spec.project_id,
                "group_by": group_by,
            },
        )
    )
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)
    assert decision.audit_id is not None

    if caller.sid:
        prior = await deps.audit_reader.session_aggregates(caller.sid)
        if overlaps_prior(req.dataset, group_by, req.filters, prior):
            await deps.audit.write(
                AuditEvent(
                    event_type="decision",
                    agent_user=subject.user_id,
                    agent_software=_agent_software(caller, deps),
                    purpose_of_event=purpose,
                    entity_resource=f"aggregate/{req.dataset}",
                    entity_query=encode_query(raw),
                    outcome=OUTCOME_MINOR,
                    outcome_desc="not_found",
                    policy_id=decision.policy_id,
                    policy_version=deps.policy_version,
                    reason_code="overlap_blocked",
                    session_id=caller.sid,
                    jti=caller.jti,
                    detail={**detail_base, "prior_decision_audit_id": str(decision.audit_id)},
                )
            )
            raise NotFound()

    raw_cells = await deps.clinical.aggregate(
        req.dataset, group_by, req.filters, decision.obligations, decision.scoped_keys
    )
    cells = apply_suppression(raw_cells, group_by, decision.obligations.k_min)
    suppressed = sum(1 for c in cells if c["suppressed"])

    await deps.audit_reader.log_aggregate(
        session_id=caller.sid,
        user_id=subject.user_id,
        dataset=req.dataset,
        group_by=group_by,
        filters=filter_equalities(req.filters),
        cells=cells,
        suppressed_cells=suppressed,
        k_min=decision.obligations.k_min,
        audit_id=decision.audit_id,
    )
    await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=subject.user_id,
            agent_software=_agent_software(caller, deps),
            purpose_of_event=purpose,
            entity_resource=f"aggregate/{req.dataset}",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="aggregate_returned",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            jti=caller.jti,
            detail={
                "decision_audit_id": str(decision.audit_id),
                "cells": len(cells),
                "suppressed": suppressed,
            },
        )
    )
    visible = [c for c in cells if not c["suppressed"]]
    return QueryResponse(
        dataset=req.dataset,
        rows=cells,
        row_count=len(visible),
        suppressed_cells=suppressed,
        obligations=decision.obligations.as_dict(),
        decision=DecisionOut(
            effect=decision.effect,
            reason_code=decision.reason_code,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            relation=decision.relation,
            purpose_of_event=purpose,
        ),
        audit_id=decision.audit_id,
    )
