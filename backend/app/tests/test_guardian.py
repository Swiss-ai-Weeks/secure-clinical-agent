"""Guardianship (Build Plan §9 step 13): Nina Haller reads her daughter Lea's record, the adolescent-clinic
rows are redacted, she exercises the patient's consent authority, and sees nothing of anyone else."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from patient360.errors import NOT_FOUND_BYTES

from .conftest import Harness
from .fakes import PII_ONLY_FIELDS, seed_demo_consents


def in_days(n: int) -> str:
    return (datetime.now(UTC) + timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _login(c: httpx.AsyncClient, who: str, **kw) -> dict:
    r = await c.post("/auth/dev-login", json={"login": who, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def _query(c: httpx.AsyncClient, patient: str, dataset: str) -> httpx.Response:
    return await c.post("/tools/query", json={"patient_key": patient, "dataset": dataset})


async def test_guardian_reads_the_minor_and_adolescent_rows_are_redacted(harness: Harness):
    me = await harness.login("haller", auth_level=2)
    assert me["role"] == "caregiver" and me["self_patient_id"] is None  # not a patient herself

    r = await _query(harness.client, "p_104", "labs")
    assert r.status_code == 200, r.text
    labs = r.json()
    assert labs["row_count"] == 2 and labs["redacted_count"] == 0
    assert (
        labs["decision"]["relation"] == "can_read_clinical"
        and labs["decision"]["reason_code"] == "relationship"
    )

    r = await _query(harness.client, "p_104", "conditions")
    body = r.json()
    assert body["row_count"] == 2 and body["redacted_count"] == 1
    redacted = [row for row in body["rows"] if row.get("redacted")]
    assert redacted == [
        {
            "cite_id": "cond_d2",
            "confidentiality": "R",
            "redacted": True,
            "redact_reason": "adolescent_confidential",
        }
    ]
    assert "Pregnancy prevention" not in r.text and "SEX" not in r.text
    assert body["obligations"]["redact"] == {"R": "adolescent_confidential", "V": "adolescent_confidential"}

    r = await _query(harness.client, "p_104", "meds")
    assert [row["display"] for row in r.json()["rows"] if not row.get("redacted")] == ["Albuterol inhaler"]
    assert "Levonorgestrel" not in r.text

    r = await _query(harness.client, "p_104", "encounters")
    assert r.json()["redacted_count"] == 1 and "adolescent-medicine" not in r.text

    decision = harness.audit.of_type("decision")[-1]
    assert decision.detail["patient_age"] == datetime.now(UTC).year - 2012
    assert decision.purpose_of_event == "PATRQT"


async def test_guardian_sees_nothing_of_other_patients(harness: Harness):
    await harness.login("haller", auth_level=2)
    for patient in ("p_101", "p_103", "p_205", "p_999"):
        r = await _query(harness.client, patient, "labs")
        assert r.status_code == 404 and r.content == NOT_FOUND_BYTES, patient
        assert (await harness.client.get(f"/patients/{patient}/identity")).status_code == 404
        assert (await harness.client.get("/consents", params={"patient": patient})).status_code == 404
    assert harness.clinical.calls == []


async def test_guardian_gets_the_identity_banner(harness: Harness):
    await harness.login("haller")
    r = await harness.client.get("/patients/p_104/identity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["given_name"] == "Lea" and body["family_name"] == "Haller" and body["birth_date"] == "2012-05-03"
    )
    for f in PII_ONLY_FIELDS:
        assert f not in body
    assert "Hardturmstrasse" not in r.text and "756.5678" not in r.text
    assert harness.audit.of_type("decision")[-1].detail["relation"] == "can_read_clinical"


async def test_guardian_exercises_the_patients_consent_authority(harness: Harness):
    """Proxy consent: grant caregiver to Diego on the child, he reads, she revokes, he cannot."""
    async with harness.new_client() as diego:
        await _login(diego, "diego", auth_level=2)
        assert (await _query(diego, "p_104", "labs")).status_code == 404

        await harness.login("haller", auth_level=2)
        r = await harness.client.post(
            "/consents",
            json={
                "patient_key": "p_104",
                "grantee_user_id": "u_diego",
                "relation": "caregiver",
                "expiry": in_days(30),
                "justification": "Lea's uncle drives her to appointments",
            },
        )
        assert r.status_code == 201, r.text
        grant = r.json()
        assert grant["granted_by"] == "u_haller" and grant["status"] == "active"
        granted = harness.audit.of_type("consent_granted")[-1]
        assert granted.detail["basis"] == "guardian" and granted.purpose_of_event == "PATRQT"
        decision = harness.audit.of_type("decision")[-1]
        assert decision.reason_code == "guardian" and decision.detail["relation"] == "can_consent"

        r = await _query(diego, "p_104", "labs")
        assert r.status_code == 200
        # An uncle named as caregiver of a 14-year-old gets the same adolescent rule.
        r = await _query(diego, "p_104", "conditions")
        assert r.json()["redacted_count"] == 1

        r = await harness.client.post(f"/consents/{grant['consent_id']}/revoke")
        assert r.status_code == 200, r.text
        assert (await _query(diego, "p_104", "labs")).status_code == 404


async def test_guardian_cannot_delegate_or_grant_to_the_wrong_role(harness: Harness):
    await harness.login("haller", auth_level=2)
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_104",
            "grantee_user_id": "u_rivera",
            "relation": "care_team",
            "expiry": in_days(7),
        },
    )
    assert r.status_code == 403
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "relation_not_grantable"
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_104",
            "grantee_user_id": "u_rivera",
            "relation": "caregiver",
            "expiry": in_days(7),
        },
    )
    assert r.status_code == 403
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "grantee_role_mismatch"
    assert harness.fga.writes == []


async def test_guardian_can_block_a_clinician_on_the_child(harness: Harness):
    from patient360.fga import Tuple, Window

    # Give Okafor a live consult on Lea, then have Nina block him.
    harness.fga.tuples.append(
        Tuple(
            "user:u_okafor",
            "consultant",
            "patient:p_104",
            Window(datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
        )
    )
    async with harness.new_client() as okafor:
        await _login(okafor, "okafor", auth_level=2)
        assert (await _query(okafor, "p_104", "labs")).status_code == 200

        await harness.login("haller")
        r = await harness.client.post(
            "/consents",
            json={
                "patient_key": "p_104",
                "grantee_user_id": "u_okafor",
                "relation": "blocked",
                "justification": "court order: no contact with this practitioner",
            },
        )
        assert r.status_code == 201, r.text
        assert (await _query(okafor, "p_104", "labs")).status_code == 404


async def test_listing_shows_the_guardianship_record(harness: Harness):
    ids = seed_demo_consents(harness.audit)
    await harness.login("haller")
    r = await harness.client.get("/consents", params={"patient": "p_104"})
    assert r.status_code == 200, r.text
    rows = {(c["grantee_user_id"], c["relation"]): c for c in r.json()["consents"]}
    g = rows[("u_haller", "guardian")]
    assert g["status"] == "active" and g["seeded"] is True and g["enforced"] is True
    assert g["consent_id"] == str(ids[("user:u_haller", "guardian", "patient:p_104")])
    assert g["expiry"].startswith("2030-05-03")  # majority
    assert harness.audit.of_type("decision")[-1].reason_code == "guardian"


async def test_guardian_who_is_also_a_patient_reads_own_record_as_self(harness: Harness):
    harness.deps.vault.mapping["u_haller"] = "p_102"
    me = await harness.login("haller")
    assert me["self_patient_id"] == "p_102"
    r = await _query(harness.client, "p_102", "conditions")
    assert r.status_code == 200  # p_102 has no fake rows; the decision is what matters
    assert r.json()["decision"]["reason_code"] == "self_match"
    assert harness.fga.calls == []  # own record: identity, not a grant
    r = await harness.client.get("/patients/p_102/identity")
    assert r.status_code == 200 and r.json()["family_name"] == "Bianchi"
    # and the child still through the guardian tuple
    assert (await _query(harness.client, "p_104", "labs")).status_code == 200


async def test_guardianship_is_not_grantable_through_the_api(harness: Harness):
    await harness.login("maria")
    r = await harness.client.post(
        "/consents", json={"patient_key": "p_103", "grantee_user_id": "u_haller", "relation": "guardian"}
    )
    assert r.status_code == 422  # not in the relation enum: guardianship is a registration act
    assert harness.fga.writes == []


async def test_adult_caregiver_is_unaffected_by_the_adolescent_rule(harness: Harness):
    await harness.login("diego", auth_level=2)  # Maria is 68
    r = await _query(harness.client, "p_103", "meds")
    assert r.status_code == 200 and r.json()["redacted_count"] == 0
    assert harness.audit.of_type("decision")[-1].detail["patient_age"] == datetime.now(UTC).year - 1958
