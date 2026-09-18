from __future__ import annotations

from patient360.redteam_run import run_suite


async def test_redteam_suite_scores(harness):
    body = await run_suite(harness.client._transport.app)
    harness.client._transport.app.state.redteam = body
    assert body["count"] >= 40
    assert body["pass"] + body["fail"] + body["partial"] == body["count"]
    assert 0 <= body["asr"] <= 1
    ids = {c["id"] for c in body["cases"]}
    assert "caregiver-notes-expired" in ids
    assert "pixel-via-tool" in ids
    assert body["pass"] >= 15


async def test_redteam_endpoint_reads_cache(harness):
    await harness.login("chen", auth_level=2)
    harness.client._transport.app.state.redteam = {
        "count": 1,
        "pass": 1,
        "fail": 0,
        "partial": 0,
        "asr": 0.0,
        "cases": [{"id": "pixel-via-tool", "result": "pass", "owasp": "LLM02"}],
    }
    r = await harness.client.get("/redteam")
    assert r.status_code == 200
    assert r.json()["cases"][0]["id"] == "pixel-via-tool"


async def test_redteam_unauthorized(harness):
    r = await harness.client.get("/redteam")
    assert r.status_code == 401
