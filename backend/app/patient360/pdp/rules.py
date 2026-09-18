"""The PDP (Build Plan §4.1). Pure over its inputs; the relation check is injected.

Evaluation order for reads:
  1. Explicit deny: agent channel with a non-read action; care role off duty;
     patient role on any key other than the session's own; dataset outside the
     role allowlist. The patient-role mismatch is a hard deny that is *reported*
     as not-found so the body is byte-identical to a nonexistent patient.
  2. Self match: patient role on own key -> permit, OpenFGA not consulted.
  3. Relationship: one OpenFGA check with current_time. false -> not_found.
  4. Obligations: label rules by role and AAL. care_team gets REDACT on R and V;
     every non-self role at AAL1 gets REDACT on V (step_up_required); dietary
     staff see food allergies only.
  5. Default deny.

Writes (consent_grant, consent_revoke, break_glass) are dashboard-only and
follow the §4.2 grant authority table: the patient's own record (self match)
for caregiver / caregiver_notes / blocked; the can_delegate permission for
care_team / consultant; care roles on duty at AAL2 for break-glass. Foreign
patients are the uniform not-found; wrong relation for the authority is a 403.

Labels are applied row-wise from the obligations, so one decision per tool call
is enough and the label never has to be known before the query runs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from .models import CARE_ROLES, Context, Decision, Obligations, Resource, Subject
from .relations import (
    AGGREGATE_DATASETS,
    AGGREGATE_DIMS,
    AUTHORITY_BY_ROLE,
    BASIS_BY_AUTHORITY,
    BREAK_GLASS_ROLES,
    GRANTABLE_BY_AUTHORITY,
    GRANTABLE_BY_SELF,
    GRANTEE_ROLE_FOR_RELATION,
    IDENTITY_BANNER_ROLES,
    IMAGING_ROLES,
    NOTES_ROLES,
    PIXEL_ROLES,
    ROLE_DATASETS,
    relation_for,
)

POLICY_ID = "patient360.pdp.v1"

RelationCheck = Callable[[str, str, str, datetime], Awaitable[bool]]
ListObjects = Callable[[str, str, str, datetime], Awaitable[list[str]]]


def _deny(reason: str) -> Decision:
    return Decision(effect="deny", reason_code=reason, policy_id=POLICY_ID)


def _not_found(reason: str, *, relation: str | None = None, consulted: bool = False) -> Decision:
    return Decision(
        effect="not_found",
        reason_code=reason,
        policy_id=POLICY_ID,
        relation=relation,
        fga_consulted=consulted,
    )


def _permit(
    reason: str,
    *,
    obligations: Obligations | None = None,
    relation: str | None = None,
    consulted: bool = False,
    scoped_keys: tuple[str, ...] | None = None,
) -> Decision:
    return Decision(
        effect="permit",
        reason_code=reason,
        policy_id=POLICY_ID,
        obligations=obligations or Obligations(),
        relation=relation,
        fga_consulted=consulted,
        scoped_keys=scoped_keys,
    )


def is_adolescent(age: int | None, context: Context) -> bool:
    return age is not None and context.adolescent_age <= age < context.majority_age


def obligations_for(
    subject: Subject, resource: Resource, context: Context, *, self_match: bool
) -> Obligations:
    ob = Obligations()
    if self_match:
        ob.exclude_internal = True
        return ob
    if subject.role == "care_team":
        ob.redact["R"] = "REDACT"
        ob.redact["V"] = "REDACT"
    if subject.role == "caregiver" and is_adolescent(resource.patient_age, context):
        # Confidential adolescent care: a guardian or named caregiver of a minor with
        # capacity of judgement does not see restricted or very restricted rows. The
        # adolescent's own login (patient role, self match) is not affected.
        ob.redact["R"] = "adolescent_confidential"
        ob.redact["V"] = "adolescent_confidential"
    if subject.auth_level < 2:
        # V needs AAL2 (NIST SP 800-63-4). Redact rather than deny the whole dataset.
        ob.redact.setdefault("V", "step_up_required")
    if subject.role == "dietary_staff":
        ob.allergy_category = "food"
    return ob


SELF_MATCH_ROLES = frozenset({"patient", "caregiver"})


def _is_self(subject: Subject, resource: Resource) -> bool:
    """Own record: the session's vault-resolved key. Patients, and caregivers who are also patients."""
    return (
        subject.role in SELF_MATCH_ROLES
        and subject.self_patient_id is not None
        and resource.patient_key == subject.self_patient_id
    )


def _object_keys(objects: list[str], type_: str) -> tuple[str, ...]:
    prefix = f"{type_}:"
    return tuple(o.removeprefix(prefix) for o in objects if o.startswith(prefix))


async def evaluate(
    subject: Subject,
    resource: Resource,
    context: Context,
    check: RelationCheck,
    *,
    list_objects: ListObjects | None = None,
) -> Decision:
    # 1. Explicit deny, common to every action.
    if context.channel == "agent" and context.action != "read":
        return _deny("agent_write_forbidden")
    if subject.role in CARE_ROLES and not subject.on_duty:
        return _deny("off_duty_step_up_required")

    # Aggregate has no patient_key (researcher) or ignores one (existence-oracle).
    if context.action == "read" and resource.type == "aggregate":
        return await _evaluate_aggregate(subject, resource, context, check, list_objects)

    if not resource.patient_key:
        return _not_found("invalid_resource")

    if context.action == "read":
        return await _evaluate_read(subject, resource, context, check)
    if context.action in ("consent_grant", "consent_revoke"):
        return await _evaluate_consent(subject, resource, context, check)
    if context.action == "break_glass":
        return _evaluate_break_glass(subject, resource, context)
    if context.action in ("schedule", "cancel"):
        return await _evaluate_schedule(subject, resource, context, check)
    return _deny("action_not_supported")


async def _evaluate_read(
    subject: Subject, resource: Resource, context: Context, check: RelationCheck
) -> Decision:
    if resource.type == "identity":
        return await _evaluate_identity(subject, resource, context, check)
    if resource.type == "consents":
        return await _evaluate_consents_list(subject, resource, context, check)
    if resource.type in ("notes", "imaging_report", "imaging_pixels", "document_bytes"):
        return await _evaluate_gated_read(subject, resource, context, check)
    if resource.type != "clinical_rows":
        return _not_found("resource_type_not_served")
    if not resource.dataset:
        return _not_found("invalid_resource")
    if subject.role == "patient" and not _is_self(subject, resource):
        return _not_found("self_mismatch")
    allowed = ROLE_DATASETS.get(subject.role, frozenset())
    if resource.dataset not in allowed:
        return _not_found("aggregate_only" if subject.role == "researcher" else "dataset_not_allowed")

    # 2. Self match.
    if _is_self(subject, resource):
        return _permit("self_match", obligations=obligations_for(subject, resource, context, self_match=True))

    # 3. Relationship.
    relation = relation_for(resource.type, resource.dataset, subject.role)
    if relation is None:
        return _not_found("no_relation_for_resource")
    held = await check(f"user:{subject.user_id}", relation, f"patient:{resource.patient_key}", context.now)
    if not held:
        return _not_found("relationship_missing_or_expired", relation=relation, consulted=True)

    # 4. Obligations.
    return _permit(
        "relationship",
        obligations=obligations_for(subject, resource, context, self_match=False),
        relation=relation,
        consulted=True,
    )


def _imaging_tier(subject: Subject, relation: str | None, *, self_match: bool) -> str:
    if self_match or subject.role in ("care_team", "caregiver") or relation == "can_read_imaging_metadata":
        return "metadata"
    return "report"


async def _evaluate_gated_read(
    subject: Subject, resource: Resource, context: Context, check: RelationCheck
) -> Decision:
    """Notes, imaging reports, and dashboard media bytes. Same deny/self/FGA order."""
    if resource.type == "notes" and subject.role not in NOTES_ROLES:
        return _not_found("notes_not_allowed")
    if resource.type == "imaging_report" and subject.role not in IMAGING_ROLES:
        return _not_found("imaging_not_allowed")
    if resource.type in ("imaging_pixels", "document_bytes") and subject.role not in PIXEL_ROLES:
        return _not_found("pixels_not_allowed")
    if subject.role == "patient" and not _is_self(subject, resource):
        return _not_found("self_mismatch")

    if _is_self(subject, resource):
        ob = obligations_for(subject, resource, context, self_match=True)
        if resource.type == "imaging_report":
            ob.imaging_tier = _imaging_tier(subject, None, self_match=True)
        return _permit("self_match", obligations=ob)

    relation = relation_for(resource.type, resource.dataset, subject.role)
    if relation is None:
        return _not_found("no_relation_for_resource")
    held = await check(f"user:{subject.user_id}", relation, f"patient:{resource.patient_key}", context.now)
    if not held:
        return _not_found("relationship_missing_or_expired", relation=relation, consulted=True)
    ob = obligations_for(subject, resource, context, self_match=False)
    if resource.type == "imaging_report":
        ob.imaging_tier = _imaging_tier(subject, relation, self_match=False)
    return _permit("relationship", obligations=ob, relation=relation, consulted=True)


async def _evaluate_identity(
    subject: Subject, resource: Resource, context: Context, check: RelationCheck
) -> Decision:
    """identity_banner: names never travel the agent channel; self or a live clinical relationship."""
    if context.channel == "agent":
        return _deny("identity_agent_forbidden")
    if subject.role == "patient":
        return _permit("self_match") if _is_self(subject, resource) else _not_found("self_mismatch")
    if _is_self(subject, resource):
        return _permit("self_match")
    if subject.role not in IDENTITY_BANNER_ROLES:
        return _not_found("identity_not_allowed")
    relation = relation_for("identity", None, subject.role)
    assert relation is not None
    held = await check(f"user:{subject.user_id}", relation, f"patient:{resource.patient_key}", context.now)
    if not held:
        return _not_found("relationship_missing_or_expired", relation=relation, consulted=True)
    return _permit("relationship", relation=relation, consulted=True)


async def _evaluate_consents_list(
    subject: Subject, resource: Resource, context: Context, check: RelationCheck
) -> Decision:
    """Who may see the consents on a record: the patient (self), a delegate, or a guardian."""
    if subject.role == "patient":
        return _permit("self_match") if _is_self(subject, resource) else _not_found("self_mismatch")
    if _is_self(subject, resource):
        return _permit("self_match")
    permission = AUTHORITY_BY_ROLE.get(subject.role)
    if permission is None:
        return _not_found("delegate_authority_missing")
    held = await check(f"user:{subject.user_id}", permission, f"patient:{resource.patient_key}", context.now)
    if not held:
        return _not_found("delegate_authority_missing", relation=permission, consulted=True)
    return _permit(BASIS_BY_AUTHORITY[permission], relation=permission, consulted=True)


async def _evaluate_consent(
    subject: Subject, resource: Resource, context: Context, check: RelationCheck
) -> Decision:
    target = context.target
    if target is None:
        return _not_found("invalid_resource")

    # Authority: self on own record; else the permission the role may hold (can_delegate for
    # attendings, can_consent for guardians). Foreign patients are the uniform not-found.
    if subject.role == "patient" and not _is_self(subject, resource):
        return _not_found("self_mismatch")
    if _is_self(subject, resource):
        grantable = GRANTABLE_BY_SELF
        basis = "self_match"
        relation_checked: str | None = None
        consulted = False
    else:
        permission = AUTHORITY_BY_ROLE.get(subject.role)
        if permission is None:
            return _not_found("delegate_authority_missing")
        held = await check(
            f"user:{subject.user_id}", permission, f"patient:{resource.patient_key}", context.now
        )
        if not held:
            return _not_found("delegate_authority_missing", relation=permission, consulted=True)
        grantable = GRANTABLE_BY_AUTHORITY[permission]
        basis = BASIS_BY_AUTHORITY[permission]
        relation_checked = permission
        consulted = True

    def deny(reason: str) -> Decision:
        return Decision(
            effect="deny",
            reason_code=reason,
            policy_id=POLICY_ID,
            relation=relation_checked,
            fga_consulted=consulted,
        )

    if target.relation not in grantable:
        return deny("relation_not_grantable")

    if context.action == "consent_grant":
        if target.grantee_user_id is None or target.grantee_user_id == subject.user_id:
            return deny("grantee_invalid")
        if target.grantee_role is None:
            return deny("grantee_unknown")
        if target.grantee_role not in GRANTEE_ROLE_FOR_RELATION.get(target.relation, frozenset()):
            return deny("grantee_role_mismatch")
    else:  # consent_revoke
        # A delegate revokes only what they granted; self and guardian act as the patient.
        if basis == "relationship" and target.granted_by != subject.user_id:
            return deny("not_granted_by_subject")

    return _permit(basis, relation=relation_checked, consulted=consulted)


def _evaluate_break_glass(subject: Subject, resource: Resource, context: Context) -> Decision:
    if subject.role not in BREAK_GLASS_ROLES:
        return _deny("break_glass_role_not_allowed")
    if subject.auth_level < 2:
        return _deny("step_up_required")
    # on_duty was checked in the common explicit-deny step.
    return _permit("break_glass")


async def _evaluate_aggregate(
    subject: Subject,
    resource: Resource,
    context: Context,
    check: RelationCheck,
    list_objects: ListObjects | None,
) -> Decision:
    """Researcher project check, attending own-cohort, dietary ward counts."""
    if not resource.dataset:
        return _not_found("invalid_resource")
    allowed = AGGREGATE_DATASETS.get(subject.role)
    if allowed is None:
        return _not_found("aggregate_role_not_allowed")
    if resource.dataset not in allowed:
        return _not_found("dataset_not_allowed")

    dims = (
        context.allowed_dims
        if context.allowed_dims is not None
        else tuple(sorted(AGGREGATE_DIMS.get(resource.dataset, frozenset())))
    )
    dim_set = frozenset(dims)
    if context.group_by and any(d not in dim_set for d in context.group_by):
        return _not_found("dim_not_allowed")

    if subject.role == "researcher":
        if not context.project_id:
            return _not_found("aggregate_project_missing")
        relation = "can_query_aggregate"
        held = await check(f"user:{subject.user_id}", relation, f"project:{context.project_id}", context.now)
        if not held:
            return _not_found("relationship_missing_or_expired", relation=relation, consulted=True)
        return _permit(
            "aggregate_project",
            obligations=Obligations(k_min=context.k_min, date_shift=True, allowed_dims=dims),
            relation=relation,
            consulted=True,
        )

    if list_objects is None:
        return _not_found("aggregate_scope_unavailable")
    relation = "can_read_diet" if subject.role == "dietary_staff" else "can_read_clinical"
    objects = await list_objects(f"user:{subject.user_id}", relation, "patient", context.now)
    keys = _object_keys(objects, "patient")
    if not keys:
        return _not_found("relationship_missing_or_expired", relation=relation, consulted=True)
    return _permit(
        "aggregate_own",
        obligations=Obligations(allowed_dims=dims),
        relation=relation,
        consulted=True,
        scoped_keys=keys,
    )


async def _evaluate_schedule(
    subject: Subject, resource: Resource, context: Context, check: RelationCheck
) -> Decision:
    """Book (can_schedule or self) or cancel (booker, practitioner, or self)."""
    if context.action == "cancel":
        if _is_self(subject, resource):
            return _permit("self_match")
        if subject.user_id in {context.appointment_created_by, context.appointment_practitioner}:
            return _permit("appointment_party")
        return _not_found("cancel_not_allowed")

    if subject.role == "patient":
        return _permit("self_match") if _is_self(subject, resource) else _not_found("self_mismatch")
    if _is_self(subject, resource):
        return _permit("self_match")
    relation = "can_schedule"
    held = await check(f"user:{subject.user_id}", relation, f"patient:{resource.patient_key}", context.now)
    if not held:
        return _not_found("relationship_missing_or_expired", relation=relation, consulted=True)
    return _permit("relationship", relation=relation, consulted=True)
