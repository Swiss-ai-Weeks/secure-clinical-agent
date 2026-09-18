"""Consent grant / revoke / list: authority, §4.2 write ordering, and §9 step 11 (live revoke)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from patient360.errors import NOT_FOUND_BYTES

from .conftest import Harness
from .fakes import seed_demo_consents


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def in_days(n: int) -> str:
    return _iso(datetime.now(UTC) + timedelta(days=n))


async def _login(c: httpx.AsyncClient, who: str, **kw) -> dict:
    r = await c.post("/auth/dev-login", json={"login": who, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def _query(c: httpx.AsyncClient, patient: str, dataset: str) -> httpx.Response:
    return await c.post("/tools/query", json={"patient_key": patient, "dataset": dataset})


async def test_patient_blocks_a_clinician_on_own_record(harness: Harness):
    await harness.login("maria")
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_103",
            "grantee_user_id": "u_okafor",
            "relation": "blocked",
            "justification": "I do not want Dr. Okafor involved in my care",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active" and body["enforced"] is True and body["consent_id"]
    assert body["start"] is None and body["expiry"] is None  # blocked has no window
    assert harness.fga.has("user:u_okafor", "blocked", "patient:p_103")

    types = [e.event_type for _, e in harness.audit.events]
    assert types[-2:] == ["decision", "consent_granted"]
    granted = harness.audit.of_type("consent_granted")[-1]
    assert granted.agent_user == "u_maria" and granted.purpose_of_event == "PATRQT"
    assert granted.detail["granted_by"] == "u_maria" and granted.detail["basis"] == "self_match"
    assert granted.detail["tuple"] == {
        "user": "user:u_okafor",
        "relation": "blocked",
        "object": "patient:p_103",
    }
    decision = harness.audit.of_type("decision")[-1]
    assert decision.reason_code == "self_match" and decision.detail["fga_consulted"] is False


async def test_duplicate_live_consent_is_409(harness: Harness):
    await harness.login("maria")
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_103",
            "grantee_user_id": "u_diego",
            "relation": "caregiver",
            "expiry": in_days(30),
        },
    )
    assert r.status_code == 409
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "consent_exists"


async def test_expired_consent_is_renewed_by_replacing_the_window(harness: Harness):
    await harness.login("maria")
    before = [t for t in harness.fga.tuples if t.key == ("user:u_diego", "caregiver_notes", "patient:p_103")][
        0
    ]
    assert not before.window.is_live(datetime.now(UTC))
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_103",
            "grantee_user_id": "u_diego",
            "relation": "caregiver_notes",
            "expiry": in_days(30),
        },
    )
    assert r.status_code == 201, r.text
    after = [t for t in harness.fga.tuples if t.key == before.key]
    assert len(after) == 1 and after[0].window.is_live(datetime.now(UTC))
    assert r.json()["status"] == "active"


async def test_delegate_grant_read_revoke_read(harness: Harness):
    """Chen delegates care_team on p_102 to Rivera; Rivera can read; Chen revokes; Rivera cannot."""
    async with harness.new_client() as rivera:
        await _login(rivera, "rivera", auth_level=2)
        assert (await _query(rivera, "p_102", "conditions")).status_code == 404

        await harness.login("chen", auth_level=2)
        r = await harness.client.post(
            "/consents",
            json={
                "patient_key": "p_102",
                "grantee_user_id": "u_rivera",
                "relation": "care_team",
                "expiry": in_days(7),
                "justification": "covering nurse this week",
            },
        )
        assert r.status_code == 201, r.text
        consent_id = r.json()["consent_id"]
        assert r.json()["granted_by"] == "u_chen"
        decision = harness.audit.of_type("decision")[-1]
        assert decision.reason_code == "relationship" and decision.detail["relation"] == "can_delegate"
        assert decision.detail["action"] == "consent_grant"

        assert (await _query(rivera, "p_102", "conditions")).status_code == 200

        r = await harness.client.post(f"/consents/{consent_id}/revoke")
        assert r.status_code == 200, r.text
        assert r.json()["tuple_removed"] is True and r.json()["revoked_at"]
        assert not harness.fga.has("user:u_rivera", "care_team", "patient:p_102")
        revoked = harness.audit.of_type("consent_revoked")[-1]
        assert revoked.detail["consent_id"] == consent_id and revoked.detail["revoked_by"] == "u_chen"

        assert (await _query(rivera, "p_102", "conditions")).status_code == 404

        r = await harness.client.get("/consents", params={"patient": "p_102"})
        assert r.status_code == 200
        rows = {(c["grantee_user_id"], c["relation"]): c for c in r.json()["consents"]}
        assert rows[("u_rivera", "care_team")]["status"] == "revoked"
        assert rows[("u_rivera", "care_team")]["revoked_by"] == "u_chen"
        assert rows[("u_rivera", "care_team")]["enforced"] is False

        r = await harness.client.post(f"/consents/{consent_id}/revoke")
        assert r.status_code == 409
        assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "already_revoked"


async def test_care_team_has_no_grant_authority_uniform_404(harness: Harness):
    await harness.login("rivera", auth_level=2)
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_101",
            "grantee_user_id": "u_okafor",
            "relation": "consultant",
            "expiry": in_days(7),
        },
    )
    assert r.status_code == 404 and r.content == NOT_FOUND_BYTES
    assert harness.audit.of_type("decision")[-1].reason_code == "delegate_authority_missing"
    assert harness.fga.writes == []


async def test_grantee_role_mismatch_and_wrong_relation_are_403(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_101",
            "grantee_user_id": "u_nair",
            "relation": "care_team",
            "expiry": in_days(7),
        },
    )
    assert r.status_code == 403
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "grantee_role_mismatch"
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_101",
            "grantee_user_id": "u_diego",
            "relation": "caregiver",
            "expiry": in_days(7),
        },
    )
    assert r.status_code == 403
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "relation_not_grantable"
    assert harness.fga.writes == []


async def test_window_validation(harness: Harness):
    await harness.login("chen", auth_level=2)
    base = {"patient_key": "p_101", "grantee_user_id": "u_rivera", "relation": "consultant"}
    base["grantee_user_id"] = "u_okafor"
    r = await harness.client.post("/consents", json={**base, "expiry": in_days(-1)})
    assert (
        r.status_code == 422 and r.json()["issue"][0]["details"]["coding"][0]["code"] == "expiry_before_start"
    )
    r = await harness.client.post("/consents", json={**base, "expiry": in_days(400)})
    assert r.status_code == 422 and r.json()["issue"][0]["details"]["coding"][0]["code"] == "window_too_long"
    r = await harness.client.post("/consents", json=base)
    assert r.status_code == 422 and r.json()["issue"][0]["details"]["coding"][0]["code"] == "expiry_required"
    assert harness.fga.writes == []


async def test_audit_failure_on_grant_deletes_the_tuple(harness: Harness):
    await harness.login("chen", auth_level=2)
    harness.audit.fail_types.add("consent_granted")
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_102",
            "grantee_user_id": "u_rivera",
            "relation": "care_team",
            "expiry": in_days(7),
        },
    )
    assert r.status_code == 503
    assert not harness.fga.has("user:u_rivera", "care_team", "patient:p_102")
    # write then delete: access never persisted without a record
    assert [(len(w), len(d)) for w, d in harness.fga.writes] == [(1, 0), (0, 1)]


async def test_revoke_retries_audit_once(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post(
        "/consents",
        json={
            "patient_key": "p_102",
            "grantee_user_id": "u_rivera",
            "relation": "care_team",
            "expiry": in_days(7),
        },
    )
    consent_id = r.json()["consent_id"]
    harness.audit.fail_once_types.add("consent_revoked")
    r = await harness.client.post(f"/consents/{consent_id}/revoke")
    assert r.status_code == 200
    assert not harness.fga.has("user:u_rivera", "care_team", "patient:p_102")
    assert len(harness.audit.of_type("consent_revoked")) == 1


async def test_step_11_patient_revokes_seeded_caregiver_consent_live(harness: Harness):
    ids = seed_demo_consents(harness.audit)
    diego_consent = ids[("user:u_diego", "caregiver", "patient:p_103")]

    async with harness.new_client() as diego:
        await _login(diego, "diego")
        assert (await _query(diego, "p_103", "meds")).status_code == 200

        await harness.login("maria")
        r = await harness.client.get("/consents", params={"patient": "p_103"})
        assert r.status_code == 200
        rows = {(c["grantee_user_id"], c["relation"]): c for c in r.json()["consents"]}
        assert rows[("u_diego", "caregiver")]["status"] == "active"
        assert rows[("u_diego", "caregiver")]["seeded"] is True
        assert rows[("u_diego", "caregiver")]["consent_id"] == str(diego_consent)
        assert rows[("u_diego", "caregiver_notes")]["status"] == "expired"

        r = await harness.client.post(f"/consents/{diego_consent}/revoke")
        assert r.status_code == 200, r.text

        assert (await _query(diego, "p_103", "meds")).status_code == 404
        assert harness.audit.of_type("decision")[-1].reason_code == "relationship_missing_or_expired"

        r = await harness.client.get("/consents", params={"patient": "p_103"})
        rows = {(c["grantee_user_id"], c["relation"]): c for c in r.json()["consents"]}
        assert rows[("u_diego", "caregiver")]["status"] == "revoked"
        assert rows[("u_diego", "caregiver")]["revoked_by"] == "u_maria"


async def test_delegate_cannot_revoke_a_grant_they_did_not_make(harness: Harness):
    ids = seed_demo_consents(harness.audit)  # rivera's care_team on p_101 was written by the worker
    await harness.login("chen", auth_level=2)
    r = await harness.client.post(f"/consents/{ids[('user:u_rivera', 'care_team', 'patient:p_101')]}/revoke")
    assert r.status_code == 403
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "not_granted_by_subject"
    assert harness.fga.has("user:u_rivera", "care_team", "patient:p_101")


async def test_listing_shows_store_only_tuples_and_is_gated(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.get("/consents", params={"patient": "p_101"})
    assert r.status_code == 200
    rows = {(c["grantee_user_id"], c["relation"]): c for c in r.json()["consents"]}
    assert rows[("u_rivera", "care_team")]["status"] == "store_only"
    assert rows[("u_okafor", "consultant")]["status"] == "store_only"
    assert rows[("u_chen", "attending")]["status"] == "store_only"
    assert ("u_lindqvist", "staff") not in rows  # placements are not consents
    assert (await harness.client.get("/consents", params={"patient": "p_205"})).status_code == 404

    async with harness.new_client() as rivera:
        await _login(rivera, "rivera")
        r = await rivera.get("/consents", params={"patient": "p_101"})
        assert r.status_code == 404 and r.content == NOT_FOUND_BYTES
    async with harness.new_client() as maria:
        await _login(maria, "maria")
        assert (await maria.get("/consents", params={"patient": "p_101"})).status_code == 404
        assert (await maria.get("/consents", params={"patient": "p_103"})).status_code == 200


async def test_consent_endpoints_refuse_run_tokens_and_anonymous(harness: Harness):
    await harness.login("chen", auth_level=2)
    token = (await harness.client.post("/dev/run-token", json={})).json()["access_token"]
    async with harness.new_client() as agent:
        h = {"Authorization": f"Bearer {token}"}
        body = {
            "patient_key": "p_101",
            "grantee_user_id": "u_okafor",
            "relation": "consultant",
            "expiry": in_days(7),
        }
        assert (await agent.post("/consents", json=body, headers=h)).status_code == 401
        assert (await agent.get("/consents", params={"patient": "p_101"}, headers=h)).status_code == 401
        assert (await agent.post("/consents", json=body)).status_code == 401
    assert harness.fga.writes == []
