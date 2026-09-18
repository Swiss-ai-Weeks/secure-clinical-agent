"""POST /tools/notes: PDP, server-side filter, uniform 404."""

from __future__ import annotations


async def test_chen_reads_p101_discharge(harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "glycemic"})
    assert r.status_code == 200, r.text
    body = r.json()
    texts = " ".join(c["text"] for c in body["chunks"])
    assert "Metformin" in texts
    assert "Psychiatric" in texts  # attending sees V


async def test_rivera_does_not_see_psych_text(harness):
    await harness.login("rivera", auth_level=2)
    r = await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "mood"})
    assert r.status_code == 200, r.text
    texts = " ".join(c.get("text") or "" for c in r.json()["chunks"])
    assert "Psychiatric" not in texts
    assert r.json()["obligations"]["redact"]["V"] == "REDACT"


async def test_diego_notes_404(harness):
    await harness.login("diego", auth_level=1)
    r = await harness.client.post("/tools/notes", json={"patient_key": "p_103", "question": "heart"})
    assert r.status_code == 404


async def test_nair_notes_404(harness):
    await harness.login("nair", auth_level=1)
    r = await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "labs"})
    assert r.status_code == 404


async def test_maria_excludes_internal_on_own_record(harness):
    await harness.login("maria", auth_level=1)
    r = await harness.client.post("/tools/notes", json={"patient_key": "p_103", "question": "hypertension"})
    assert r.status_code == 200, r.text
    assert r.json()["obligations"]["exclude_internal"] is True
    assert any("amlodipine" in (c.get("text") or "").lower() for c in r.json()["chunks"])


async def test_filter_is_server_built(harness):
    await harness.login("chen", auth_level=2)
    await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "discharge"})
    assert harness.deps.notes.calls[-1]["patient_key"] == "p_101"
    assert harness.deps.notes.calls[-1]["published"] is True
