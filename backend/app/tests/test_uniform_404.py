"""Unauthorized and nonexistent patients are byte-identical 404s; no cookie is a 401 before the PDP."""

from __future__ import annotations

from patient360.errors import NOT_FOUND_BYTES

from .conftest import Harness

VOLATILE_HEADERS = {"date", "server"}


def _stable_headers(r) -> dict[str, str]:
    return {k.lower(): v for k, v in r.headers.items() if k.lower() not in VOLATILE_HEADERS}


async def test_unassigned_and_nonexistent_are_identical(harness: Harness):
    await harness.login("chen", auth_level=2)
    r_unassigned = await harness.client.post("/tools/query", json={"patient_key": "p_205", "dataset": "labs"})
    r_missing = await harness.client.post("/tools/query", json={"patient_key": "p_999", "dataset": "labs"})
    assert r_unassigned.status_code == r_missing.status_code == 404
    assert r_unassigned.content == r_missing.content == NOT_FOUND_BYTES
    assert _stable_headers(r_unassigned) == _stable_headers(r_missing)
    assert b"p_205" not in r_unassigned.content and b"p_999" not in r_missing.content
    # The store was never touched for either.
    assert harness.clinical.calls == []


async def test_researcher_patient_role_and_expired_grant_all_return_the_same_bytes(harness: Harness):
    bodies = []
    for login, patient in (("nair", "p_101"), ("maria", "p_101"), ("okafor", "p_102"), ("diego", "p_101")):
        async with harness.new_client() as c:
            r = await c.post("/auth/dev-login", json={"login": login})
            assert r.status_code == 200
            r = await c.post("/tools/query", json={"patient_key": patient, "dataset": "meds"})
            assert r.status_code == 404
            bodies.append(r.content)
    assert all(b == NOT_FOUND_BYTES for b in bodies)
    reasons = [ev.reason_code for ev in harness.audit.of_type("decision")]
    assert reasons == [
        "aggregate_only",
        "self_mismatch",
        "relationship_missing_or_expired",
        "relationship_missing_or_expired",
    ]


async def test_unauthenticated_is_401_before_any_decision(harness: Harness):
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 401
    assert harness.audit.events == []
    r = await harness.client.get("/me")
    assert r.status_code == 401


async def test_deny_carries_reason_and_audit_id(harness: Harness):
    await harness.login("chen", on_duty=False)
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 403
    body = r.json()
    assert body["issue"][0]["details"]["coding"][0]["code"] == "off_duty_step_up_required"
    audit_id = body["extension"][0]["valueString"]
    assert any(str(aid) == audit_id for aid, _ in harness.audit.events)


async def test_audit_failure_fails_closed(harness: Harness):
    await harness.login("chen", auth_level=2)
    harness.audit.fail = True
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 503
    assert harness.clinical.calls == []


async def test_fga_failure_fails_closed(harness: Harness):
    await harness.login("chen", auth_level=2)
    harness.fga.fail = True
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 503
    assert harness.clinical.calls == []
