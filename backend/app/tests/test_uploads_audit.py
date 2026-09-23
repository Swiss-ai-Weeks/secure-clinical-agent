from __future__ import annotations

from patient360.guardrails import REFUSAL, RailResult
from patient360.nemo_rails import NemoRails


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


async def _quarantine_upload(harness, monkeypatch, rail: RailResult):
    published: list = []
    original = harness.deps.notes.upsert

    async def spy(points, **kwargs):
        published.append(points)
        return await original(points, **kwargs)

    monkeypatch.setattr(harness.deps.notes, "upsert", spy)

    async def verdict(self, text):
        return rail

    monkeypatch.setattr(NemoRails, "check_document", verdict)
    harness.settings.safety_url = "http://safety:8000"
    await harness.login("maria", auth_level=1)
    response = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_103"},
        files={"file": ("note.txt", b"Blood pressure log. No identifiers.", "text/plain")},
    )
    return response, published


async def test_unsafe_document_is_not_published(harness, monkeypatch):
    response, published = await _quarantine_upload(
        harness, monkeypatch, RailResult(False, "content_safety", REFUSAL)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "quarantine"
    assert response.json()["reason"] == "content_safety"
    assert published == []


async def test_safety_nim_error_does_not_publish(harness, monkeypatch):
    response, published = await _quarantine_upload(
        harness, monkeypatch, RailResult(False, "content_safety_unavailable", REFUSAL)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "quarantine"
    assert response.json()["reason"] == "content_safety_unavailable"
    assert published == []


def _pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET\n".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


async def test_pdf_upload_is_published_for_the_model(harness):
    await harness.login("maria", auth_level=1)
    response = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_103"},
        files={"file": ("Backilyan.pdf", _pdf("Blood pressure log from the scan."), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "processed"
    notes = await harness.client.post(
        "/tools/notes", json={"patient_key": "p_103", "question": "pressure"}
    )
    assert notes.status_code == 200
    texts = " ".join(c["text"] for c in notes.json()["chunks"])
    assert "Blood pressure" in texts


async def test_pdf_without_text_stays_not_text(harness, monkeypatch):
    async def unexpected(self, text):
        raise AssertionError("safety NIM was called")

    monkeypatch.setattr(NemoRails, "check_document", unexpected)
    harness.settings.safety_url = "http://safety:8000"
    await harness.login("maria", auth_level=1)
    response = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_103"},
        files={"file": ("scan.pdf", _pdf(""), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "quarantine"
    assert response.json()["reason"] == "not_text"


async def test_image_upload_stays_not_text_without_safety_call(harness, monkeypatch):
    async def unexpected(self, text):
        raise AssertionError("safety NIM was called")

    monkeypatch.setattr(NemoRails, "check_document", unexpected)
    harness.settings.safety_url = "http://safety:8000"
    await harness.login("maria", auth_level=1)
    response = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_103"},
        files={"file": ("scan.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "quarantine"
    assert response.json()["reason"] == "not_text"


async def test_clinician_upload_is_clinical_and_deletes(harness):
    await harness.login("chen", auth_level=2)
    response = await harness.client.post(
        "/uploads",
        data={"patient_key": "p_101"},
        files={"file": ("Backilyan.txt", b"Clinic upload marker from the attending.", "text/plain")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "processed"
    assert body["provenance"] == "clinical"
    notes = await harness.client.post(
        "/tools/notes", json={"patient_key": "p_101", "question": "marker"}
    )
    assert notes.status_code == 200
    match = [note for note in notes.json()["notes"] if note.get("note_id") == body["documentId"]]
    assert match and match[0]["provenance"] == "clinical"
    removed = await harness.client.request(
        "DELETE", "/uploads", json={"patient_key": "p_101", "document_id": body["documentId"]}
    )
    assert removed.status_code == 200, removed.text
    again = await harness.client.post("/tools/notes", json={"patient_key": "p_101", "question": "marker"})
    texts = " ".join(note.get("text") or "" for note in again.json()["notes"])
    assert "Clinic upload marker" not in texts


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
