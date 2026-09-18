from __future__ import annotations


async def test_chen_imaging_report_text(harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post("/tools/imaging", json={"patient_key": "p_101"})
    assert r.status_code == 200, r.text
    assert r.json()["reports"][0]["conclusion_text"]


async def test_rivera_imaging_metadata_only(harness):
    await harness.login("rivera", auth_level=2)
    r = await harness.client.post("/tools/imaging", json={"patient_key": "p_101"})
    assert r.status_code == 200, r.text
    assert "conclusion_text" not in r.json()["reports"][0]


async def test_nair_imaging_404(harness):
    await harness.login("nair", auth_level=1)
    r = await harness.client.post("/tools/imaging", json={"patient_key": "p_101"})
    assert r.status_code == 404


async def test_media_sign_and_cross_session(harness):
    await harness.login("chen", auth_level=2)
    await harness.deps.objects.put("reports", "study-1", b"DICOM")
    signed = await harness.client.post("/media/sign", json={"patient_key": "p_101", "study_id": "study-1"})
    assert signed.status_code == 200, signed.text
    url = signed.json()["url"]
    fetched = await harness.client.get(url)
    assert fetched.status_code == 200

    other = harness.new_client()
    await other.post("/auth/dev-login", json={"login": "okafor", "on_duty": True, "auth_level": 2})
    replay = await other.get(url)
    assert replay.status_code == 401


async def test_rivera_cannot_sign_pixels(harness):
    await harness.login("rivera", auth_level=2)
    r = await harness.client.post("/media/sign", json={"patient_key": "p_101", "study_id": "study-1"})
    assert r.status_code == 404
