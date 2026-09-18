"""Sessions: rotation, logout, /me manifest, identity in tool args ignored, audit rows per action."""

from __future__ import annotations

from .conftest import Harness


async def test_login_sets_cookie_and_me_returns_manifest(harness: Harness):
    body = await harness.login("chen", auth_level=2)
    assert body["role"] == "attending" and body["self_patient_id"] is None
    cookie = harness.client.cookies.get(harness.settings.cookie_name)
    assert cookie and len(cookie) == 32  # 128-bit hex
    r = await harness.client.get("/me")
    assert r.status_code == 200
    me = r.json()
    assert me["user_id"] == "u_chen" and me["display"] == "Dr. Sarah Chen"
    assert me["policy_version"] == "fga:test-model"
    assert "diet" in me["datasets"] and "break_glass" in me["panels"]
    assert me["session"]["auth_level"] == 2 and me["session"]["on_duty"] is True
    assert [e.event_type for _, e in harness.audit.events] == ["login"]


async def test_patient_login_resolves_self_from_vault_and_audits_it(harness: Harness):
    body = await harness.login("maria")
    assert body["self_patient_id"] == "p_103"
    types = [e.event_type for _, e in harness.audit.events]
    assert types == ["identity_resolve", "login"]
    resolve = harness.audit.of_type("identity_resolve")[0]
    assert resolve.entity_patient == "p_103" and resolve.purpose_of_event == "PATRQT"
    me = (await harness.client.get("/me")).json()
    assert me["self_patient_id"] == "p_103" and "portal" in me["panels"]


async def test_caregiver_without_vault_link_has_no_self_key(harness: Harness):
    body = await harness.login("diego")
    assert body["self_patient_id"] is None


async def test_login_rotates_session(harness: Harness):
    await harness.login("chen")
    first = harness.client.cookies.get(harness.settings.cookie_name)
    await harness.login("chen")
    second = harness.client.cookies.get(harness.settings.cookie_name)
    assert first != second
    async with harness.new_client() as stale:
        stale.cookies.set(harness.settings.cookie_name, first)
        assert (await stale.get("/me")).status_code == 401
    assert harness.audit.of_type("login")[-1].detail["rotated"] is True


async def test_logout_ends_session(harness: Harness):
    await harness.login("chen")
    assert (await harness.client.post("/auth/logout")).status_code == 204
    assert (await harness.client.get("/me")).status_code == 401
    assert [e.event_type for _, e in harness.audit.events] == ["login", "logout"]


async def test_unknown_login_is_401(harness: Harness):
    r = await harness.client.post("/auth/dev-login", json={"login": "nobody"})
    assert r.status_code == 401
    assert harness.audit.events == []


async def test_identity_in_tool_args_is_ignored_and_logged(harness: Harness):
    await harness.login("nair")
    r = await harness.client.post(
        "/tools/query",
        json={"patient_key": "p_101", "dataset": "labs", "user_id": "u_chen", "role": "attending", "foo": 1},
    )
    assert r.status_code == 404  # still the researcher
    decision = harness.audit.of_type("decision")[-1]
    assert decision.agent_user == "u_nair"
    assert decision.detail["ignored_args"] == ["foo", "role", "user_id"]
    assert decision.detail["ignored_identity_args"] == ["role", "user_id"]
    assert decision.entity_query  # base64 of the parameters as received


async def test_permitted_read_writes_decision_then_tool_call(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 200
    body = r.json()
    types = [e.event_type for _, e in harness.audit.events]
    assert types == ["login", "decision", "tool_call"]
    decision_id, decision = [(aid, e) for aid, e in harness.audit.events if e.event_type == "decision"][0]
    assert str(decision_id) == body["audit_id"]
    assert decision.policy_version == "fga:test-model" and decision.purpose_of_event == "TREAT"
    assert decision.entity_patient == "p_101" and decision.entity_resource == "clinical_rows/labs"
    # session id on the row is the hex of session_hash and matches the live session
    assert decision.session_id and len(decision.session_id) == 64
    assert bytes.fromhex(decision.session_id) in harness.sessions.rows
    tool_call = harness.audit.of_type("tool_call")[0]
    assert tool_call.detail == {"decision_audit_id": body["audit_id"], "rows": 2, "redacted": 0}


async def test_aggregate_without_project_is_404(harness: Harness):
    await harness.login("nair")
    r = await harness.client.post(
        "/tools/query", json={"patient_key": "p_101", "dataset": "labs", "aggregate": {"group_by": ["code"]}}
    )
    assert r.status_code == 404
    assert harness.audit.of_type("decision")[-1].reason_code == "aggregate_project_missing"


async def test_audit_read_own_rows_and_auditor(harness: Harness):
    await harness.login("chen", auth_level=2)
    body = (
        await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    ).json()
    r = await harness.client.get(f"/audit/{body['audit_id']}")
    assert r.status_code == 200 and r.json()["agent_user"] == "u_chen"
    async with harness.new_client() as other:
        await other.post("/auth/dev-login", json={"login": "rivera"})
        assert (await other.get(f"/audit/{body['audit_id']}")).status_code == 404
    # auditor role: seed one via the fake user table
    harness.deps.devlogin._by_login["audit"] = type(harness.deps.devlogin.personas()[0])(
        "audit", "u_audit", "Auditor"
    )
    async with harness.new_client() as auditor:
        await auditor.post("/auth/dev-login", json={"login": "audit"})
        assert (await auditor.get(f"/audit/{body['audit_id']}")).status_code == 200
