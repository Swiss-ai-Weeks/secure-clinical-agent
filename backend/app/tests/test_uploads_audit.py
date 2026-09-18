from __future__ import annotations


async def test_maria_upload_sanitized_note(harness):
    await harness.login("maria", auth_level=1)
    r = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_103"},
        files={"file": ("note.txt", b"Blood pressure log. No identifiers.", "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processed"
    notes = await harness.client.post("/tools/notes", json={"patient_key": "p_103", "question": "pressure"})
    assert notes.status_code == 200
    texts = " ".join(c["text"] for c in notes.json()["chunks"])
    assert "Blood pressure" in texts


async def test_diego_upload_foreign_404(harness):
    await harness.login("diego", auth_level=1)
    r = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_101"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 404


async def test_audit_list_own_events(harness):
    await harness.login("chen", auth_level=2)
    await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    r = await harness.client.get("/audit")
    assert r.status_code == 200
    assert r.json()["events"]
