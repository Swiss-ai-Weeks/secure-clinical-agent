"""identity_banner: names only for self or a live relationship, dashboard only, banner fields only."""

from __future__ import annotations

import httpx

from patient360.errors import NOT_FOUND_BYTES

from .conftest import Harness
from .fakes import IDENTITIES, PII_ONLY_FIELDS

BANNER_KEYS = {"patient_key", "given_name", "family_name", "birth_date", "sex", "mrn"}
META_KEYS = {"purpose_of_event", "compliance_flag", "audit_id", "identity_audit_id"}


async def _login(c: httpx.AsyncClient, who: str, **kw) -> dict:
    r = await c.post("/auth/dev-login", json={"login": who, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _assert_no_pii(text: str) -> None:
    for ident in IDENTITIES.values():
        assert ident.phone not in text
        assert ident.national_id not in text
        assert ident.address["line"] not in text


async def test_attending_gets_banner_fields_only(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.get("/patients/p_101/identity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == BANNER_KEYS | META_KEYS
    assert body["given_name"] == "Elisabeth" and body["family_name"] == "Keller"
    assert body["birth_date"] == "1961-04-17" and body["mrn"] == "MRN-4471902"
    assert body["purpose_of_event"] == "TREAT" and body["compliance_flag"] is False
    for f in PII_ONLY_FIELDS:
        assert f not in body
    _assert_no_pii(r.text)

    types = [e.event_type for _, e in harness.audit.events]
    assert types[-2:] == ["decision", "identity_resolve"]
    decision, resolve = [e for _, e in harness.audit.events][-2:]
    assert (
        decision.entity_resource == "identity/banner" and decision.detail["relation"] == "can_read_clinical"
    )
    assert resolve.detail["operation"] == "identity_banner" and resolve.detail["resolved"] is True
    assert resolve.detail["decision_audit_id"] == body["audit_id"]


async def test_relationship_and_role_gating(harness: Harness):
    cases = [
        ("rivera", "p_101", 200),  # care team
        ("okafor", "p_101", 200),  # consultant in window
        ("okafor", "p_102", 404),  # expired consult
        ("diego", "p_103", 200),  # caregiver
        ("diego", "p_101", 404),
        ("nair", "p_101", 404),  # researcher never
        ("lindqvist", "p_101", 404),  # dietary staff never
        ("chen", "p_205", 404),  # no relationship
        ("chen", "p_999", 404),  # nonexistent
    ]
    for who, patient, status in cases:
        async with harness.new_client() as c:
            await _login(c, who, auth_level=2)
            r = await c.get(f"/patients/{patient}/identity")
            assert r.status_code == status, (who, patient, r.text)
            if status == 404:
                assert r.content == NOT_FOUND_BYTES
            _assert_no_pii(r.text)


async def test_patient_sees_own_banner_without_fga(harness: Harness):
    await harness.login("maria")
    r = await harness.client.get("/patients/p_103/identity")
    assert r.status_code == 200
    assert r.json()["family_name"] == "Santos" and r.json()["purpose_of_event"] == "PATRQT"
    assert harness.fga.calls == []
    r = await harness.client.get("/patients/p_101/identity")
    assert r.status_code == 404 and r.content == NOT_FOUND_BYTES
    assert harness.audit.of_type("decision")[-1].reason_code == "self_mismatch"


async def test_banner_under_break_glass_is_btg(harness: Harness):
    await harness.login("chen", auth_level=2)
    assert (await harness.client.get("/patients/p_205/identity")).status_code == 404
    r = await harness.client.post(
        "/break-glass",
        json={"patient_key": "p_205", "justification": "Collapsed in the waiting room, unknown history"},
    )
    assert r.status_code == 201
    r = await harness.client.get("/patients/p_205/identity")
    assert r.status_code == 200
    assert r.json()["family_name"] == "Weber"
    assert r.json()["purpose_of_event"] == "BTG" and r.json()["compliance_flag"] is True
    assert harness.audit.of_type("identity_resolve")[-1].purpose_of_event == "BTG"


async def test_identity_never_travels_the_agent_channel(harness: Harness):
    await harness.login("chen", auth_level=2)
    token = (await harness.client.post("/dev/run-token", json={})).json()["access_token"]
    async with harness.new_client() as agent:
        r = await agent.get("/patients/p_101/identity", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert (await agent.get("/patients/p_101/identity")).status_code == 401
    assert harness.audit.of_type("identity_resolve") == []


async def test_missing_vault_record_is_uniform_404(harness: Harness):
    harness.deps.vault.identities.pop("p_101")
    await harness.login("chen", auth_level=2)
    r = await harness.client.get("/patients/p_101/identity")
    assert r.status_code == 404 and r.content == NOT_FOUND_BYTES
    resolve = harness.audit.of_type("identity_resolve")[-1]
    assert resolve.detail["resolved"] is False and resolve.outcome == "4"


async def test_vault_unavailable_fails_closed(harness: Harness):
    from patient360.errors import Transient

    class DownVault:
        async def resolve_self(self, user_id):
            return None

        async def read_identity(self, patient_key):
            raise Transient("vault down")

    harness.deps.vault = DownVault()
    await harness.login("chen", auth_level=2)
    assert (await harness.client.get("/patients/p_101/identity")).status_code == 503


async def test_lindqvist_lists_ward_patients_not_clinical_roster(harness: Harness):
    await harness.login("lindqvist", auth_level=1)
    r = await harness.client.get("/patients")
    assert r.status_code == 200, r.text
    keys = r.json()["patient_keys"]
    assert "p_101" in keys
    assert "p_102" not in keys
    assert "p_205" not in keys


async def test_chen_lists_granted_patients(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.get("/patients")
    assert r.status_code == 200, r.text
    keys = r.json()["patient_keys"]
    assert "p_101" in keys and "p_102" in keys
    assert "p_205" not in keys


async def test_lindqvist_lists_ward_patients_not_clinical_roster(harness: Harness):
    await harness.login("lindqvist", auth_level=1)
    r = await harness.client.get("/patients")
    assert r.status_code == 200, r.text
    keys = r.json()["patient_keys"]
    assert "p_101" in keys
    assert "p_102" not in keys
    assert "p_205" not in keys


async def test_maria_lists_only_self(harness: Harness):
    await harness.login("maria", auth_level=1)
    r = await harness.client.get("/patients")
    assert r.status_code == 200
    assert r.json()["patient_keys"] == ["p_103"]
