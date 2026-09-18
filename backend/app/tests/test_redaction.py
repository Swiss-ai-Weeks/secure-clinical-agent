"""REDACT obligations applied row-wise; visible evidence is the count and the label, not the content."""

from __future__ import annotations

from patient360.pdp.models import Obligations
from patient360.tools.query import apply_redaction

from .conftest import Harness


def test_apply_redaction_keeps_only_handle_and_label():
    rows = [
        {"cite_id": "a", "display": "Diabetes", "confidentiality": "N", "sensitivity": []},
        {"cite_id": "b", "display": "Depression", "confidentiality": "V", "sensitivity": ["PSY"]},
        {"cite_id": "c", "display": "Sertraline", "confidentiality": "R", "sensitivity": ["PSY"]},
    ]
    out, n = apply_redaction(rows, Obligations(redact={"V": "REDACT"}))
    assert n == 1
    assert out[0] == rows[0]
    assert out[1] == {"cite_id": "b", "confidentiality": "V", "redacted": True, "redact_reason": "REDACT"}
    assert out[2] == rows[2]
    assert "sensitivity" not in out[1] and "display" not in out[1]


def test_no_obligation_is_identity():
    rows = [{"cite_id": "a", "confidentiality": "V"}]
    assert apply_redaction(rows, Obligations()) == (rows, 0)


async def test_care_team_sees_psych_condition_redacted(harness: Harness):
    await harness.login("rivera", auth_level=2)
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "conditions"})
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 2 and body["redacted_count"] == 1
    redacted = [row for row in body["rows"] if row.get("redacted")]
    assert redacted == [
        {"cite_id": "cond_a2", "confidentiality": "V", "redacted": True, "redact_reason": "REDACT"}
    ]
    assert body["obligations"]["redact"] == {"R": "REDACT", "V": "REDACT"}
    assert "Depressive" not in r.text and "PSY" not in r.text


async def test_attending_at_aal2_sees_everything(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "conditions"})
    body = r.json()
    assert body["redacted_count"] == 0
    assert any(row["display"] == "Depressive disorder" for row in body["rows"])


async def test_attending_at_aal1_gets_step_up_marker(harness: Harness):
    await harness.login("chen", auth_level=1)
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "meds"})
    body = r.json()
    # R (sertraline) is visible at AAL1 for an attending; only V is gated.
    assert body["redacted_count"] == 0
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "conditions"})
    body = r.json()
    assert body["redacted_count"] == 1
    assert [row["redact_reason"] for row in body["rows"] if row.get("redacted")] == ["step_up_required"]


async def test_dietary_staff_food_allergies_only(harness: Harness):
    await harness.login("lindqvist")
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "allergies"})
    assert r.status_code == 200
    body = r.json()
    assert [row["display"] for row in body["rows"]] == ["Peanut"]
    assert body["obligations"]["allergy_category"] == "food"
    assert body["decision"]["relation"] == "can_read_diet"
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 404


async def test_self_view_returns_own_rows_without_fga(harness: Harness):
    me = await harness.login("maria")
    assert me["self_patient_id"] == "p_103"
    r = await harness.client.post("/tools/query", json={"patient_key": "p_103", "dataset": "meds"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["reason_code"] == "self_match"
    assert body["obligations"] == {"exclude_internal": True}
    assert harness.fga.calls == []
