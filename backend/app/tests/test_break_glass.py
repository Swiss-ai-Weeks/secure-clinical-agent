"""Break-glass (Build Plan §9 step 10): typed justification, time-boxed emergency tuple, BTG rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from patient360.fga import Tuple, parse_rfc3339

from .conftest import Harness
from .fakes import PII_ONLY_FIELDS

JUSTIFICATION = "Unresponsive patient in ED, prior records needed for anticoagulation decision"


async def _login(c: httpx.AsyncClient, who: str, **kw) -> dict:
    r = await c.post("/auth/dev-login", json={"login": who, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def _bg(
    c: httpx.AsyncClient, patient: str = "p_205", justification: str = JUSTIFICATION
) -> httpx.Response:
    return await c.post("/break-glass", json={"patient_key": patient, "justification": justification})


async def _query(c: httpx.AsyncClient, patient: str, dataset: str) -> httpx.Response:
    return await c.post("/tools/query", json={"patient_key": patient, "dataset": dataset})


async def test_step_10_chen_break_glass_on_p205(harness: Harness):
    await harness.login("chen", auth_level=2)
    assert (await _query(harness.client, "p_205", "labs")).status_code == 404

    r = await _bg(harness.client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["compliance_flag"] is True
    start, expiry = parse_rfc3339(body["start"]), parse_rfc3339(body["expiry"])
    assert expiry - start == timedelta(minutes=harness.settings.break_glass_minutes)
    assert abs((start - datetime.now(UTC)).total_seconds()) < 5

    # The tuple is time-boxed exactly to the window on the audit row.
    tup = [t for t in harness.fga.tuples if t.key == ("user:u_chen", "emergency", "patient:p_205")]
    assert len(tup) == 1 and tup[0].window.start == start and tup[0].window.expiry == expiry

    types = [e.event_type for _, e in harness.audit.events]
    assert types[-3:] == ["decision", "break_glass", "identity_resolve"]
    decision, bg, ident = [e for _, e in harness.audit.events][-3:]
    assert decision.purpose_of_event == "BTG" and decision.reason_code == "break_glass"
    assert bg.purpose_of_event == "BTG" and bg.entity_patient == "p_205"
    assert bg.detail["justification"] == JUSTIFICATION and bg.detail["compliance_flag"] is True
    assert parse_rfc3339(bg.detail["expiry"]) == expiry and parse_rfc3339(bg.detail["start"]) == start
    assert ident.purpose_of_event == "BTG" and ident.detail["operation"] == "break_glass_identity"
    assert ident.detail["break_glass_audit_id"] == body["audit_id"]

    # break_glass_identity returns the banner and nothing more.
    assert body["identity"] == {
        "patient_key": "p_205",
        "given_name": "Jonas",
        "family_name": "Weber",
        "birth_date": "1989-02-09",
        "sex": "male",
        "mrn": "MRN-4472051",
    }
    for f in PII_ONLY_FIELDS:
        assert f not in body["identity"]
    assert "Bundesplatz" not in r.text and "756.4567" not in r.text

    # Subsequent reads are permitted and labelled BTG with the compliance flag.
    r = await _query(harness.client, "p_205", "labs")
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["row_count"] == 1
    assert q["decision"]["compliance_flag"] is True and q["decision"]["purpose_of_event"] == "BTG"
    read_decision = harness.audit.of_type("decision")[-1]
    assert read_decision.purpose_of_event == "BTG"
    assert read_decision.detail["compliance_flag"] is True
    assert read_decision.detail["break_glass_audit_id"] == body["audit_id"]
    assert harness.audit.of_type("tool_call")[-1].purpose_of_event == "BTG"

    # Reads of a patient without an activation stay TREAT.
    r = await _query(harness.client, "p_101", "labs")
    assert r.json()["decision"]["compliance_flag"] is False
    assert r.json()["decision"]["purpose_of_event"] == "TREAT"


async def test_break_glass_requires_aal2_on_duty_and_a_care_role(harness: Harness):
    cases = [
        ("chen", dict(auth_level=1), "step_up_required"),
        ("chen", dict(auth_level=2, on_duty=False), "off_duty_step_up_required"),
        ("lindqvist", dict(auth_level=2), "break_glass_role_not_allowed"),
        ("nair", dict(auth_level=2), "break_glass_role_not_allowed"),
        ("maria", dict(auth_level=2), "break_glass_role_not_allowed"),
        ("diego", dict(auth_level=2), "break_glass_role_not_allowed"),
    ]
    for who, kw, reason in cases:
        async with harness.new_client() as c:
            await _login(c, who, **kw)
            r = await _bg(c)
            assert r.status_code == 403, (who, r.text)
            assert r.json()["issue"][0]["details"]["coding"][0]["code"] == reason, who
            assert r.json()["extension"][0]["valueString"]  # decision audit id
    assert harness.fga.writes == []
    assert harness.audit.of_type("break_glass") == []


async def test_break_glass_is_dashboard_only(harness: Harness):
    await harness.login("chen", auth_level=2)
    token = (await harness.client.post("/dev/run-token", json={})).json()["access_token"]
    async with harness.new_client() as agent:
        r = await agent.post(
            "/break-glass",
            json={"patient_key": "p_205", "justification": JUSTIFICATION},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
        assert (await _bg(agent)).status_code == 401
    assert harness.fga.writes == []


async def test_justification_is_required_and_typed(harness: Harness):
    await harness.login("chen", auth_level=2)
    assert (await _bg(harness.client, justification="too short")).status_code == 422
    r = await harness.client.post("/break-glass", json={"patient_key": "p_205"})
    assert r.status_code == 422
    assert harness.fga.writes == []


async def test_audit_failure_deletes_the_emergency_tuple(harness: Harness):
    await harness.login("chen", auth_level=2)
    harness.audit.fail_types.add("break_glass")
    r = await _bg(harness.client)
    assert r.status_code == 503
    assert not harness.fga.has("user:u_chen", "emergency", "patient:p_205")
    assert (await _query(harness.client, "p_205", "labs")).status_code == 404


async def test_repeat_activation_replaces_the_window(harness: Harness):
    await harness.login("chen", auth_level=2)
    first = (await _bg(harness.client)).json()
    second = (await _bg(harness.client)).json()
    assert second["audit_id"] != first["audit_id"]
    tuples = [t for t in harness.fga.tuples if t.key == ("user:u_chen", "emergency", "patient:p_205")]
    assert len(tuples) == 1 and tuples[0].window.expiry == parse_rfc3339(second["expiry"])


async def test_rate_limit_per_user(harness: Harness):
    await harness.login("chen", auth_level=2)
    for patient in ("p_205", "p_103", "p_101"):
        assert (await _bg(harness.client, patient)).status_code == 201
    r = await _bg(harness.client, "p_102")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert not harness.fga.has("user:u_chen", "emergency", "patient:p_102")
    # another clinician is not affected
    async with harness.new_client() as okafor:
        await _login(okafor, "okafor", auth_level=2)
        assert (await _bg(okafor, "p_102")).status_code == 201


async def test_blocked_beats_break_glass_inside_the_store(harness: Harness):
    harness.fga.tuples.append(Tuple("user:u_chen", "blocked", "patient:p_102"))
    await harness.login("chen", auth_level=2)
    r = await _bg(harness.client, "p_102")
    assert r.status_code == 201  # the activation is recorded ...
    assert harness.fga.has("user:u_chen", "emergency", "patient:p_102")
    r = await _query(harness.client, "p_102", "labs")
    assert r.status_code == 404  # ... but blocked is deny-overrides on every permission
    assert harness.audit.of_type("decision")[-1].reason_code == "relationship_missing_or_expired"


async def test_identity_missing_from_vault_still_opens_access(harness: Harness):
    harness.deps.vault.identities.pop("p_205")
    await harness.login("chen", auth_level=2)
    r = await _bg(harness.client)
    assert r.status_code == 201
    assert r.json()["identity"] is None
    assert harness.audit.of_type("identity_resolve")[-1].outcome == "4"
    assert (await _query(harness.client, "p_205", "labs")).status_code == 200
