"""POST /tools/notes: PDP, server-side filter, uniform 404."""

from __future__ import annotations

from patient360.tools.notes import notes_from_chunks


def test_upload_chunk_keeps_the_filename():
    cards = notes_from_chunks(
        [
            {
                "note_id": "notes/p_101/Backilyan.pdf.txt",
                "cite_id": "abcd1234",
                "patient_key": "p_101",
                "provenance": "patient-reported",
                "text": "Co-Founder and COO.",
                "published": True,
            }
        ]
    )
    assert cards[0]["type_display"] == "Backilyan.pdf"
    assert cards[0]["sanitized_ref"] == "notes/p_101/Backilyan.pdf.txt"
    assert cards[0]["provenance"] == "patient-reported"


async def test_signed_file_pointer_follows_pixel_access(harness):
    row = harness.deps.clinical.rows[("notes", "p_101")][0]
    row["sanitized_ref"] = "notes/p_101/p_101-historical-pneumonia.pdf"
    row["type_display"] = "Historical pneumonia"

    await harness.login("chen", auth_level=2)
    chen = await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "pneumonia"})
    assert chen.status_code == 200, chen.text
    chen_note = next(note for note in chen.json()["notes"] if note.get("type_display") == "Historical pneumonia")
    assert chen_note["sanitized_ref"].endswith(".pdf")
    assert "Metformin" in chen_note["text"]

    await harness.login("rivera", auth_level=2)
    rivera = await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "pneumonia"})
    assert rivera.status_code == 200, rivera.text
    rivera_note = next(note for note in rivera.json()["notes"] if note.get("type_display") == "Historical pneumonia")
    assert "sanitized_ref" not in rivera_note
    assert "Metformin" in rivera_note["text"]


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
