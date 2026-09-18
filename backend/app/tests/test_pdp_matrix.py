"""Persona x dataset x patient -> effect, reason, obligations. Mirrors store.fga.yaml and Build Plan §9."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from patient360.pdp import Context, Resource, Subject, WriteTarget, evaluate

from .fakes import USERS, FakeFga

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def subject(
    user_id: str, *, on_duty: bool = True, auth_level: int = 2, self_patient_id: str | None = None
) -> Subject:
    u = USERS[user_id]
    return Subject(u.user_id, u.role, u.department, u.credential_level, on_duty, auth_level, self_patient_id)


def resource(patient_key: str, dataset: str = "labs") -> Resource:
    return Resource(type="clinical_rows", patient_key=patient_key, dataset=dataset)


def ctx(channel: str = "dashboard", action: str = "read") -> Context:
    return Context(now=NOW, channel=channel, purpose="TREAT", action=action)  # type: ignore[arg-type]


# (description, subject kwargs, patient, dataset, expected effect, expected reason, fga consulted)
MATRIX = [
    ("chen attending on p_101", dict(user_id="u_chen"), "p_101", "labs", "permit", "relationship", True),
    ("chen on p_102", dict(user_id="u_chen"), "p_102", "conditions", "permit", "relationship", True),
    (
        "chen on unassigned p_205",
        dict(user_id="u_chen"),
        "p_205",
        "labs",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "chen on nonexistent p_999",
        dict(user_id="u_chen"),
        "p_999",
        "labs",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "chen off duty",
        dict(user_id="u_chen", on_duty=False),
        "p_101",
        "labs",
        "deny",
        "off_duty_step_up_required",
        False,
    ),
    (
        "rivera care team in window",
        dict(user_id="u_rivera"),
        "p_101",
        "conditions",
        "permit",
        "relationship",
        True,
    ),
    ("okafor consultant active", dict(user_id="u_okafor"), "p_101", "meds", "permit", "relationship", True),
    (
        "okafor consult expired",
        dict(user_id="u_okafor"),
        "p_102",
        "meds",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "okafor has no diet",
        dict(user_id="u_okafor"),
        "p_101",
        "diet",
        "not_found",
        "dataset_not_allowed",
        False,
    ),
    (
        "nair researcher per-patient",
        dict(user_id="u_nair"),
        "p_101",
        "labs",
        "not_found",
        "aggregate_only",
        False,
    ),
    (
        "maria on foreign key",
        dict(user_id="u_maria", self_patient_id="p_103"),
        "p_101",
        "labs",
        "not_found",
        "self_mismatch",
        False,
    ),
    (
        "maria on own record",
        dict(user_id="u_maria", self_patient_id="p_103"),
        "p_103",
        "meds",
        "permit",
        "self_match",
        False,
    ),
    (
        "maria without vault link",
        dict(user_id="u_maria", self_patient_id=None),
        "p_103",
        "meds",
        "not_found",
        "self_mismatch",
        False,
    ),
    ("diego caregiver meds", dict(user_id="u_diego"), "p_103", "meds", "permit", "relationship", True),
    (
        "diego pivots to p_101",
        dict(user_id="u_diego"),
        "p_101",
        "meds",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "lindqvist diet via ward chain",
        dict(user_id="u_lindqvist"),
        "p_101",
        "diet",
        "permit",
        "relationship",
        True,
    ),
    (
        "lindqvist food allergies",
        dict(user_id="u_lindqvist"),
        "p_101",
        "allergies",
        "permit",
        "relationship",
        True,
    ),
    (
        "lindqvist labs not allowed",
        dict(user_id="u_lindqvist"),
        "p_101",
        "labs",
        "not_found",
        "dataset_not_allowed",
        False,
    ),
    (
        "lindqvist other ward patient",
        dict(user_id="u_lindqvist"),
        "p_103",
        "diet",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "lindqvist off shift (off duty)",
        dict(user_id="u_lindqvist", on_duty=False),
        "p_101",
        "diet",
        "deny",
        "off_duty_step_up_required",
        False,
    ),
    (
        "auditor reads nothing clinical",
        dict(user_id="u_audit"),
        "p_101",
        "labs",
        "not_found",
        "dataset_not_allowed",
        False,
    ),
]


@pytest.mark.parametrize(
    "desc,subj,patient,dataset,effect,reason,consulted", MATRIX, ids=[m[0] for m in MATRIX]
)
async def test_matrix(desc, subj, patient, dataset, effect, reason, consulted):
    fga = FakeFga()
    d = await evaluate(subject(**subj), resource(patient, dataset), ctx(), fga.check)
    assert d.effect == effect, desc
    assert d.reason_code == reason, desc
    assert d.fga_consulted is consulted, desc
    assert (len(fga.calls) == 1) is consulted, desc


async def test_relation_chosen_per_dataset():
    fga = FakeFga()
    await evaluate(subject("u_chen"), resource("p_101", "labs"), ctx(), fga.check)
    await evaluate(subject("u_chen"), resource("p_101", "diet"), ctx(), fga.check)
    await evaluate(subject("u_lindqvist"), resource("p_101", "allergies"), ctx(), fga.check)
    await evaluate(subject("u_chen"), resource("p_101", "allergies"), ctx(), fga.check)
    relations = [c[1] for c in fga.calls]
    assert relations == ["can_read_clinical", "can_read_diet", "can_read_diet", "can_read_clinical"]
    # current_time travels with every check
    assert all(c[3] == NOW for c in fga.calls)


async def test_obligations_care_team_redacts_r_and_v():
    d = await evaluate(
        subject("u_rivera", auth_level=2), resource("p_101", "conditions"), ctx(), FakeFga().check
    )
    assert d.obligations.redact == {"R": "REDACT", "V": "REDACT"}


async def test_obligations_aal1_redacts_v_with_step_up():
    d = await evaluate(
        subject("u_chen", auth_level=1), resource("p_101", "conditions"), ctx(), FakeFga().check
    )
    assert d.obligations.redact == {"V": "step_up_required"}
    d2 = await evaluate(
        subject("u_chen", auth_level=2), resource("p_101", "conditions"), ctx(), FakeFga().check
    )
    assert d2.obligations.redact == {}


async def test_obligations_care_team_role_rule_wins_over_aal_rule():
    d = await evaluate(subject("u_rivera", auth_level=1), resource("p_101", "labs"), ctx(), FakeFga().check)
    assert d.obligations.redact["V"] == "REDACT"


async def test_obligations_self_excludes_internal_and_never_redacts():
    d = await evaluate(
        subject("u_maria", auth_level=1, self_patient_id="p_103"), resource("p_103"), ctx(), FakeFga().check
    )
    assert d.permitted
    assert d.obligations.exclude_internal is True
    assert d.obligations.redact == {}


async def test_obligations_dietary_food_only():
    d = await evaluate(
        subject("u_lindqvist", auth_level=1), resource("p_101", "allergies"), ctx(), FakeFga().check
    )
    assert d.obligations.allergy_category == "food"


async def test_agent_channel_cannot_write():
    d = await evaluate(
        subject("u_chen"), resource("p_101"), ctx(channel="agent", action="schedule"), FakeFga().check
    )
    assert d.effect == "deny"
    assert d.reason_code == "agent_write_forbidden"


async def test_agent_channel_reads_like_dashboard():
    d = await evaluate(subject("u_chen"), resource("p_101"), ctx(channel="agent"), FakeFga().check)
    assert d.permitted


async def test_fga_error_propagates_as_transient_never_permit():
    from patient360.errors import Transient

    fga = FakeFga()
    fga.fail = True
    with pytest.raises(Transient):
        await evaluate(subject("u_chen"), resource("p_101"), ctx(), fga.check)


NOTES_MATRIX = [
    ("chen notes p_101", dict(user_id="u_chen"), "p_101", "permit", "relationship", True),
    ("rivera notes p_101", dict(user_id="u_rivera"), "p_101", "permit", "relationship", True),
    (
        "diego notes expired",
        dict(user_id="u_diego"),
        "p_103",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "maria own notes",
        dict(user_id="u_maria", self_patient_id="p_103", auth_level=1),
        "p_103",
        "permit",
        "self_match",
        False,
    ),
    (
        "maria foreign notes",
        dict(user_id="u_maria", self_patient_id="p_103", auth_level=1),
        "p_101",
        "not_found",
        "self_mismatch",
        False,
    ),
    ("nair notes", dict(user_id="u_nair"), "p_101", "not_found", "notes_not_allowed", False),
    ("lindqvist notes", dict(user_id="u_lindqvist"), "p_101", "not_found", "notes_not_allowed", False),
    ("haller notes child", dict(user_id="u_haller"), "p_104", "permit", "relationship", True),
]


@pytest.mark.parametrize(
    "desc,subj,patient,effect,reason,consulted", NOTES_MATRIX, ids=[m[0] for m in NOTES_MATRIX]
)
async def test_notes_matrix(desc, subj, patient, effect, reason, consulted):
    fga = FakeFga()
    d = await evaluate(subject(**subj), Resource(type="notes", patient_key=patient), ctx(), fga.check)
    assert (d.effect, d.reason_code, d.fga_consulted) == (effect, reason, consulted), desc
    if consulted and d.permitted:
        assert fga.calls[0][1] == "can_read_notes"


async def test_rivera_notes_redact_r_and_v():
    d = await evaluate(
        subject("u_rivera"), Resource(type="notes", patient_key="p_101"), ctx(), FakeFga().check
    )
    assert d.permitted
    assert d.obligations.redact == {"R": "REDACT", "V": "REDACT"}


async def test_maria_notes_exclude_internal():
    d = await evaluate(
        subject("u_maria", self_patient_id="p_103"),
        Resource(type="notes", patient_key="p_103"),
        ctx(),
        FakeFga().check,
    )
    assert d.obligations.exclude_internal is True


IMAGING_MATRIX = [
    ("chen report", dict(user_id="u_chen"), "imaging_report", "p_101", "permit", "relationship"),
    ("rivera metadata", dict(user_id="u_rivera"), "imaging_report", "p_101", "permit", "relationship"),
    (
        "diego imaging",
        dict(user_id="u_diego"),
        "imaging_report",
        "p_103",
        "not_found",
        "relationship_missing_or_expired",
    ),
    ("nair imaging", dict(user_id="u_nair"), "imaging_report", "p_101", "not_found", "imaging_not_allowed"),
    ("chen pixels", dict(user_id="u_chen"), "imaging_pixels", "p_101", "permit", "relationship"),
    ("rivera pixels", dict(user_id="u_rivera"), "imaging_pixels", "p_101", "not_found", "pixels_not_allowed"),
    (
        "maria own pixels",
        dict(user_id="u_maria", self_patient_id="p_103", auth_level=1),
        "imaging_pixels",
        "p_103",
        "permit",
        "self_match",
    ),
]


@pytest.mark.parametrize(
    "desc,subj,rtype,patient,effect,reason", IMAGING_MATRIX, ids=[m[0] for m in IMAGING_MATRIX]
)
async def test_imaging_matrix(desc, subj, rtype, patient, effect, reason):
    d = await evaluate(subject(**subj), Resource(type=rtype, patient_key=patient), ctx(), FakeFga().check)
    assert (d.effect, d.reason_code) == (effect, reason), desc


async def test_imaging_tier_metadata_for_care_team():
    d = await evaluate(
        subject("u_rivera"), Resource(type="imaging_report", patient_key="p_101"), ctx(), FakeFga().check
    )
    assert d.obligations.imaging_tier == "metadata"
    d = await evaluate(
        subject("u_chen"), Resource(type="imaging_report", patient_key="p_101"), ctx(), FakeFga().check
    )
    assert d.obligations.imaging_tier == "report"


# --- Writes: Build Plan §4.2 grant authority ----------------------------------


def wctx(action: str, relation: str, *, grantee: str | None = None, granted_by: str | None = None) -> Context:
    grantee_role = USERS[grantee].role if grantee in USERS else None
    return Context(
        now=NOW,
        channel="dashboard",
        purpose="PATRQT",
        action=action,  # type: ignore[arg-type]
        target=WriteTarget(
            relation=relation, grantee_user_id=grantee, grantee_role=grantee_role, granted_by=granted_by
        ),
    )


MARIA = dict(user_id="u_maria", self_patient_id="p_103", auth_level=1)

# (description, subject kwargs, patient, context, effect, reason, consulted)
WRITE_MATRIX = [
    (
        "maria grants caregiver to diego",
        MARIA,
        "p_103",
        wctx("consent_grant", "caregiver", grantee="u_diego"),
        "permit",
        "self_match",
        False,
    ),
    (
        "maria grants caregiver_notes to diego",
        MARIA,
        "p_103",
        wctx("consent_grant", "caregiver_notes", grantee="u_diego"),
        "permit",
        "self_match",
        False,
    ),
    (
        "maria blocks okafor",
        MARIA,
        "p_103",
        wctx("consent_grant", "blocked", grantee="u_okafor"),
        "permit",
        "self_match",
        False,
    ),
    (
        "maria cannot grant care_team",
        MARIA,
        "p_103",
        wctx("consent_grant", "care_team", grantee="u_rivera"),
        "deny",
        "relation_not_grantable",
        False,
    ),
    (
        "maria on a foreign record",
        MARIA,
        "p_101",
        wctx("consent_grant", "caregiver", grantee="u_diego"),
        "not_found",
        "self_mismatch",
        False,
    ),
    (
        "maria grants caregiver to a clinician",
        MARIA,
        "p_103",
        wctx("consent_grant", "caregiver", grantee="u_rivera"),
        "deny",
        "grantee_role_mismatch",
        False,
    ),
    (
        "maria grants to herself",
        MARIA,
        "p_103",
        wctx("consent_grant", "caregiver", grantee="u_maria"),
        "deny",
        "grantee_invalid",
        False,
    ),
    (
        "maria grants to an unknown user",
        MARIA,
        "p_103",
        wctx("consent_grant", "caregiver", grantee="u_nobody"),
        "deny",
        "grantee_unknown",
        False,
    ),
    (
        "maria revokes regardless of granter",
        MARIA,
        "p_103",
        wctx("consent_revoke", "caregiver", granted_by="u_someone"),
        "permit",
        "self_match",
        False,
    ),
    (
        "chen delegates care_team on p_101",
        dict(user_id="u_chen"),
        "p_101",
        wctx("consent_grant", "care_team", grantee="u_rivera"),
        "permit",
        "relationship",
        True,
    ),
    (
        "chen refers consultant on p_102",
        dict(user_id="u_chen"),
        "p_102",
        wctx("consent_grant", "consultant", grantee="u_okafor"),
        "permit",
        "relationship",
        True,
    ),
    (
        "chen cannot grant caregiver",
        dict(user_id="u_chen"),
        "p_101",
        wctx("consent_grant", "caregiver", grantee="u_diego"),
        "deny",
        "relation_not_grantable",
        True,
    ),
    (
        "chen cannot block",
        dict(user_id="u_chen"),
        "p_101",
        wctx("consent_grant", "blocked", grantee="u_okafor"),
        "deny",
        "relation_not_grantable",
        True,
    ),
    (
        "chen on unassigned p_205",
        dict(user_id="u_chen"),
        "p_205",
        wctx("consent_grant", "care_team", grantee="u_rivera"),
        "not_found",
        "delegate_authority_missing",
        True,
    ),
    (
        "chen grants care_team to a researcher",
        dict(user_id="u_chen"),
        "p_101",
        wctx("consent_grant", "care_team", grantee="u_nair"),
        "deny",
        "grantee_role_mismatch",
        True,
    ),
    (
        "chen revokes own grant",
        dict(user_id="u_chen"),
        "p_101",
        wctx("consent_revoke", "care_team", granted_by="u_chen"),
        "permit",
        "relationship",
        True,
    ),
    (
        "chen revokes someone else's grant",
        dict(user_id="u_chen"),
        "p_101",
        wctx("consent_revoke", "care_team", granted_by="u_other"),
        "deny",
        "not_granted_by_subject",
        True,
    ),
    (
        "chen off duty cannot grant",
        dict(user_id="u_chen", on_duty=False),
        "p_101",
        wctx("consent_grant", "care_team", grantee="u_rivera"),
        "deny",
        "off_duty_step_up_required",
        False,
    ),
    # Roles with no authority mapping are refused without consulting the store.
    (
        "rivera has no grant authority",
        dict(user_id="u_rivera"),
        "p_101",
        wctx("consent_grant", "consultant", grantee="u_okafor"),
        "not_found",
        "delegate_authority_missing",
        False,
    ),
    (
        "okafor has no grant authority",
        dict(user_id="u_okafor"),
        "p_101",
        wctx("consent_grant", "care_team", grantee="u_rivera"),
        "not_found",
        "delegate_authority_missing",
        False,
    ),
    # A caregiver is checked for can_consent (guardianship); Diego holds none.
    (
        "diego cannot grant",
        dict(user_id="u_diego"),
        "p_103",
        wctx("consent_grant", "caregiver", grantee="u_diego"),
        "not_found",
        "delegate_authority_missing",
        True,
    ),
    # Guardian: the patient's own set, on the minor's record only, via can_consent.
    (
        "haller grants caregiver on the child",
        dict(user_id="u_haller"),
        "p_104",
        wctx("consent_grant", "caregiver", grantee="u_diego"),
        "permit",
        "guardian",
        True,
    ),
    (
        "haller grants caregiver_notes on the child",
        dict(user_id="u_haller"),
        "p_104",
        wctx("consent_grant", "caregiver_notes", grantee="u_diego"),
        "permit",
        "guardian",
        True,
    ),
    (
        "haller blocks a clinician on the child",
        dict(user_id="u_haller"),
        "p_104",
        wctx("consent_grant", "blocked", grantee="u_okafor"),
        "permit",
        "guardian",
        True,
    ),
    (
        "haller cannot delegate care_team",
        dict(user_id="u_haller"),
        "p_104",
        wctx("consent_grant", "care_team", grantee="u_rivera"),
        "deny",
        "relation_not_grantable",
        True,
    ),
    (
        "haller on another patient",
        dict(user_id="u_haller"),
        "p_103",
        wctx("consent_grant", "caregiver", grantee="u_diego"),
        "not_found",
        "delegate_authority_missing",
        True,
    ),
    (
        "haller revokes regardless of granter",
        dict(user_id="u_haller"),
        "p_104",
        wctx("consent_revoke", "caregiver", granted_by="u_someone"),
        "permit",
        "guardian",
        True,
    ),
    (
        "haller grants to a clinician as caregiver",
        dict(user_id="u_haller"),
        "p_104",
        wctx("consent_grant", "caregiver", grantee="u_rivera"),
        "deny",
        "grantee_role_mismatch",
        True,
    ),
    # A caregiver who is also a patient acts as self on the own record.
    (
        "caregiver self on own record",
        dict(user_id="u_diego", self_patient_id="p_102"),
        "p_102",
        wctx("consent_grant", "blocked", grantee="u_okafor"),
        "permit",
        "self_match",
        False,
    ),
]

EXPECTED_PERMISSION = {"u_chen": "can_delegate", "u_diego": "can_consent", "u_haller": "can_consent"}


@pytest.mark.parametrize(
    "desc,subj,patient,context,effect,reason,consulted", WRITE_MATRIX, ids=[m[0] for m in WRITE_MATRIX]
)
async def test_consent_authority_matrix(desc, subj, patient, context, effect, reason, consulted):
    fga = FakeFga()
    d = await evaluate(subject(**subj), Resource(type="consents", patient_key=patient), context, fga.check)
    assert d.effect == effect, desc
    assert d.reason_code == reason, desc
    assert d.fga_consulted is consulted, desc
    if consulted:
        assert fga.calls[0][1] == EXPECTED_PERMISSION[subj["user_id"]]


async def test_consent_write_on_agent_channel_is_denied():
    c = Context(
        now=NOW,
        channel="agent",
        purpose="PATRQT",
        action="consent_grant",
        target=WriteTarget("caregiver", "u_diego", "caregiver"),
    )
    d = await evaluate(subject(**MARIA), Resource(type="consents", patient_key="p_103"), c, FakeFga().check)
    assert d.effect == "deny" and d.reason_code == "agent_write_forbidden"


async def test_consent_write_without_target_is_not_found():
    c = Context(now=NOW, channel="dashboard", purpose="PATRQT", action="consent_grant")
    d = await evaluate(subject(**MARIA), Resource(type="consents", patient_key="p_103"), c, FakeFga().check)
    assert d.effect == "not_found" and d.reason_code == "invalid_resource"


# --- Break-glass ----------------------------------------------------------------


def bg(channel: str = "dashboard") -> Context:
    return Context(now=NOW, channel=channel, purpose="BTG", action="break_glass")  # type: ignore[arg-type]


BREAK_GLASS_MATRIX = [
    ("chen AAL2 on duty", dict(user_id="u_chen", auth_level=2), "permit", "break_glass"),
    ("chen AAL1", dict(user_id="u_chen", auth_level=1), "deny", "step_up_required"),
    ("chen off duty", dict(user_id="u_chen", on_duty=False), "deny", "off_duty_step_up_required"),
    ("rivera care team AAL2", dict(user_id="u_rivera", auth_level=2), "permit", "break_glass"),
    ("okafor consultant AAL2", dict(user_id="u_okafor", auth_level=2), "permit", "break_glass"),
    ("lindqvist dietary", dict(user_id="u_lindqvist", auth_level=2), "deny", "break_glass_role_not_allowed"),
    ("nair researcher", dict(user_id="u_nair", auth_level=2), "deny", "break_glass_role_not_allowed"),
    (
        "maria patient",
        dict(user_id="u_maria", auth_level=2, self_patient_id="p_103"),
        "deny",
        "break_glass_role_not_allowed",
    ),
    ("diego caregiver", dict(user_id="u_diego", auth_level=2), "deny", "break_glass_role_not_allowed"),
]


@pytest.mark.parametrize(
    "desc,subj,effect,reason", BREAK_GLASS_MATRIX, ids=[m[0] for m in BREAK_GLASS_MATRIX]
)
async def test_break_glass_matrix(desc, subj, effect, reason):
    fga = FakeFga()
    d = await evaluate(subject(**subj), Resource(type="clinical_rows", patient_key="p_205"), bg(), fga.check)
    assert (d.effect, d.reason_code) == (effect, reason), desc
    assert fga.calls == []  # break-glass never consults the grant store; it writes to it afterwards


async def test_break_glass_on_agent_channel_is_denied():
    d = await evaluate(
        subject("u_chen"), Resource(type="clinical_rows", patient_key="p_205"), bg("agent"), FakeFga().check
    )
    assert d.effect == "deny" and d.reason_code == "agent_write_forbidden"


# --- Identity banner and consent listing -----------------------------------------


def rctx(rtype: str, channel: str = "dashboard") -> tuple[Resource, Context]:
    return Resource(type=rtype, patient_key="p_101"), Context(now=NOW, channel=channel, purpose="TREAT")  # type: ignore[arg-type]


IDENTITY_MATRIX = [
    ("chen on own patient", dict(user_id="u_chen"), "p_101", "permit", "relationship", True),
    (
        "chen on unassigned",
        dict(user_id="u_chen"),
        "p_205",
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    ("rivera care team", dict(user_id="u_rivera"), "p_101", "permit", "relationship", True),
    ("diego caregiver", dict(user_id="u_diego"), "p_103", "permit", "relationship", True),
    ("nair researcher", dict(user_id="u_nair"), "p_101", "not_found", "identity_not_allowed", False),
    ("lindqvist dietary", dict(user_id="u_lindqvist"), "p_101", "not_found", "identity_not_allowed", False),
    ("maria self", MARIA, "p_103", "permit", "self_match", False),
    ("maria foreign", MARIA, "p_101", "not_found", "self_mismatch", False),
]


@pytest.mark.parametrize(
    "desc,subj,patient,effect,reason,consulted", IDENTITY_MATRIX, ids=[m[0] for m in IDENTITY_MATRIX]
)
async def test_identity_matrix(desc, subj, patient, effect, reason, consulted):
    fga = FakeFga()
    d = await evaluate(subject(**subj), Resource(type="identity", patient_key=patient), ctx(), fga.check)
    assert (d.effect, d.reason_code, d.fga_consulted) == (effect, reason, consulted), desc
    if consulted:
        assert fga.calls[0][1] == "can_read_clinical"


async def test_identity_never_travels_the_agent_channel():
    d = await evaluate(
        subject("u_chen"),
        Resource(type="identity", patient_key="p_101"),
        ctx(channel="agent"),
        FakeFga().check,
    )
    assert d.effect == "deny" and d.reason_code == "identity_agent_forbidden"


CONSENTS_LIST_MATRIX = [
    ("maria lists own", MARIA, "p_103", "permit", "self_match"),
    ("maria lists foreign", MARIA, "p_101", "not_found", "self_mismatch"),
    ("chen lists p_101", dict(user_id="u_chen"), "p_101", "permit", "relationship"),
    ("rivera cannot list", dict(user_id="u_rivera"), "p_101", "not_found", "delegate_authority_missing"),
    ("diego cannot list", dict(user_id="u_diego"), "p_103", "not_found", "delegate_authority_missing"),
    ("haller lists the child's", dict(user_id="u_haller"), "p_104", "permit", "guardian"),
    (
        "haller cannot list others",
        dict(user_id="u_haller"),
        "p_103",
        "not_found",
        "delegate_authority_missing",
    ),
]


# --- Guardianship reads and the adolescent rule ------------------------------------


def aged(patient: str, age: int | None, dataset: str = "conditions") -> Resource:
    return Resource(type="clinical_rows", patient_key=patient, dataset=dataset, patient_age=age)


async def test_guardian_reads_the_minor_through_can_read_clinical():
    fga = FakeFga()
    d = await evaluate(subject("u_haller", auth_level=2), aged("p_104", 14, "labs"), ctx(), fga.check)
    assert d.permitted and d.relation == "can_read_clinical" and fga.calls[0][1] == "can_read_clinical"
    d = await evaluate(subject("u_haller", auth_level=2), aged("p_103", 68, "labs"), ctx(), FakeFga().check)
    assert d.effect == "not_found" and d.reason_code == "relationship_missing_or_expired"


async def test_adolescent_rows_are_redacted_for_caregiver_role_readers():
    d = await evaluate(subject("u_haller", auth_level=2), aged("p_104", 14), ctx(), FakeFga().check)
    assert d.obligations.redact == {"R": "adolescent_confidential", "V": "adolescent_confidential"}
    # Below the threshold a guardian sees everything (AAL2).
    d = await evaluate(subject("u_haller", auth_level=2), aged("p_104", 9), ctx(), FakeFga().check)
    assert d.obligations.redact == {}
    # The rule is role + age, so a named caregiver of a teenager gets it too ...
    d = await evaluate(subject("u_diego", auth_level=2), aged("p_103", 15), ctx(), FakeFga().check)
    assert d.obligations.redact == {"R": "adolescent_confidential", "V": "adolescent_confidential"}
    # ... and a caregiver of an adult does not.
    d = await evaluate(subject("u_diego", auth_level=2), aged("p_103", 68), ctx(), FakeFga().check)
    assert d.obligations.redact == {}
    # Unknown age: no adolescent rule.
    d = await evaluate(subject("u_diego", auth_level=2), aged("p_103", None), ctx(), FakeFga().check)
    assert d.obligations.redact == {}


async def test_adolescent_rule_wins_over_the_aal_rule_and_thresholds_are_context():
    d = await evaluate(subject("u_haller", auth_level=1), aged("p_104", 14), ctx(), FakeFga().check)
    assert d.obligations.redact["V"] == "adolescent_confidential"
    c = Context(now=NOW, channel="dashboard", purpose="PATRQT", adolescent_age=16, majority_age=18)
    d = await evaluate(subject("u_haller", auth_level=2), aged("p_104", 14), c, FakeFga().check)
    assert d.obligations.redact == {}
    c = Context(now=NOW, channel="dashboard", purpose="PATRQT", adolescent_age=14, majority_age=16)
    d = await evaluate(subject("u_haller", auth_level=2), aged("p_104", 16), c, FakeFga().check)
    assert d.obligations.redact == {}


async def test_adolescent_rule_never_touches_clinicians_or_self():
    d = await evaluate(subject("u_chen", auth_level=2), aged("p_104", 14), ctx(), FakeFga([]).check)
    assert d.effect == "not_found"  # no tuple, but the point is the rule below
    fga = FakeFga()
    from datetime import UTC, datetime

    from patient360.fga import Tuple, Window

    fga.tuples.append(
        Tuple("user:u_chen", "attending", "patient:p_104", Window(NOW, datetime(2027, 1, 1, tzinfo=UTC)))
    )
    d = await evaluate(subject("u_chen", auth_level=2), aged("p_104", 14), ctx(), fga.check)
    assert d.permitted and d.obligations.redact == {}
    d = await evaluate(
        subject("u_maria", auth_level=1, self_patient_id="p_104"), aged("p_104", 14), ctx(), FakeFga().check
    )
    assert d.permitted and d.reason_code == "self_match" and d.obligations.redact == {}


async def test_caregiver_self_match_reads_own_record_without_fga():
    fga = FakeFga()
    d = await evaluate(
        subject("u_haller", self_patient_id="p_102"), aged("p_102", 51, "meds"), ctx(), fga.check
    )
    assert d.permitted and d.reason_code == "self_match" and d.obligations.exclude_internal is True
    assert fga.calls == []


async def test_guardian_identity_banner():
    fga = FakeFga()
    d = await evaluate(subject("u_haller"), Resource(type="identity", patient_key="p_104"), ctx(), fga.check)
    assert d.permitted and d.relation == "can_read_clinical"
    d = await evaluate(
        subject("u_haller"), Resource(type="identity", patient_key="p_103"), ctx(), FakeFga().check
    )
    assert d.effect == "not_found"
    d = await evaluate(
        subject("u_haller", self_patient_id="p_102"),
        Resource(type="identity", patient_key="p_102"),
        ctx(),
        FakeFga().check,
    )
    assert d.permitted and d.reason_code == "self_match"


@pytest.mark.parametrize(
    "desc,subj,patient,effect,reason", CONSENTS_LIST_MATRIX, ids=[m[0] for m in CONSENTS_LIST_MATRIX]
)
async def test_consents_list_matrix(desc, subj, patient, effect, reason):
    d = await evaluate(
        subject(**subj), Resource(type="consents", patient_key=patient), ctx(), FakeFga().check
    )
    assert (d.effect, d.reason_code) == (effect, reason), desc


AGGREGATE_MATRIX = [
    ("nair project", dict(user_id="u_nair"), "conditions", "cohort_2026", "permit", "aggregate_project"),
    (
        "nair missing project",
        dict(user_id="u_nair"),
        "conditions",
        None,
        "not_found",
        "aggregate_project_missing",
    ),
    ("chen own cohort", dict(user_id="u_chen"), "conditions", None, "permit", "aggregate_own"),
    ("lindqvist ward", dict(user_id="u_lindqvist"), "diet", None, "permit", "aggregate_own"),
    ("lindqvist labs", dict(user_id="u_lindqvist"), "labs", None, "not_found", "dataset_not_allowed"),
    (
        "maria",
        dict(user_id="u_maria", self_patient_id="p_103"),
        "conditions",
        None,
        "not_found",
        "aggregate_role_not_allowed",
    ),
    ("rivera", dict(user_id="u_rivera"), "conditions", None, "not_found", "aggregate_role_not_allowed"),
    ("haller", dict(user_id="u_haller"), "conditions", None, "not_found", "aggregate_role_not_allowed"),
]


@pytest.mark.parametrize(
    "desc,subj,dataset,project,effect,reason", AGGREGATE_MATRIX, ids=[m[0] for m in AGGREGATE_MATRIX]
)
async def test_aggregate_matrix(desc, subj, dataset, project, effect, reason):
    fga = FakeFga()
    d = await evaluate(
        subject(**subj),
        Resource(type="aggregate", dataset=dataset),
        Context(
            now=NOW,
            channel="dashboard",
            purpose="HRESCH",
            action="read",
            group_by=("code",) if dataset != "diet" else ("ward",),
            project_id=project,
            k_min=5,
        ),
        fga.check,
        list_objects=fga.list_objects,
    )
    assert (d.effect, d.reason_code) == (effect, reason), desc


# --- Schedule / cancel -----------------------------------------------------------


SCHEDULE_MATRIX = [
    ("maria books self", MARIA, "p_103", "schedule", None, None, "permit", "self_match", False),
    ("maria books foreign", MARIA, "p_101", "schedule", None, None, "not_found", "self_mismatch", False),
    (
        "diego books maria",
        dict(user_id="u_diego"),
        "p_103",
        "schedule",
        None,
        None,
        "permit",
        "relationship",
        True,
    ),
    (
        "diego books other",
        dict(user_id="u_diego"),
        "p_101",
        "schedule",
        None,
        None,
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "chen books own",
        dict(user_id="u_chen"),
        "p_101",
        "schedule",
        None,
        None,
        "permit",
        "relationship",
        True,
    ),
    (
        "chen books maria",
        dict(user_id="u_chen"),
        "p_103",
        "schedule",
        None,
        None,
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    (
        "nair cannot book",
        dict(user_id="u_nair"),
        "p_101",
        "schedule",
        None,
        None,
        "not_found",
        "relationship_missing_or_expired",
        True,
    ),
    ("maria cancels self", MARIA, "p_103", "cancel", "u_diego", "u_okafor", "permit", "self_match", False),
    (
        "booker cancels",
        dict(user_id="u_diego"),
        "p_103",
        "cancel",
        "u_diego",
        "u_okafor",
        "permit",
        "appointment_party",
        False,
    ),
    (
        "practitioner cancels",
        dict(user_id="u_okafor"),
        "p_103",
        "cancel",
        "u_maria",
        "u_okafor",
        "permit",
        "appointment_party",
        False,
    ),
    (
        "chen cannot cancel maria",
        dict(user_id="u_chen"),
        "p_103",
        "cancel",
        "u_maria",
        "u_okafor",
        "not_found",
        "cancel_not_allowed",
        False,
    ),
]


@pytest.mark.parametrize(
    "desc,subj,patient,action,created_by,practitioner,effect,reason,consulted",
    SCHEDULE_MATRIX,
    ids=[m[0] for m in SCHEDULE_MATRIX],
)
async def test_schedule_matrix(
    desc, subj, patient, action, created_by, practitioner, effect, reason, consulted
):
    fga = FakeFga()
    d = await evaluate(
        subject(**subj),
        resource(patient, "encounters"),
        Context(
            now=NOW,
            channel="dashboard",
            purpose="TREAT",
            action=action,
            appointment_created_by=created_by,
            appointment_practitioner=practitioner,
        ),
        fga.check,
    )
    assert (d.effect, d.reason_code, d.fga_consulted) == (effect, reason, consulted), desc
