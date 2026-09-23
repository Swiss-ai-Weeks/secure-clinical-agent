"""Chat failure behavior through its HTTP API with an external adapter simulator."""

import logging

import httpx


async def test_sandbox_startup_failure_is_visible_and_fail_closed(harness, monkeypatch, caplog):
    harness.settings.openshell_url = "http://adapter.test"
    await harness.login("chen", auth_level=2)
    original_client = httpx.AsyncClient

    def adapter(request):
        assert request.url.path == "/v1/sandboxes", "A turn cannot run without a session sandbox"
        return httpx.Response(503, json={"error": "RuntimeError", "detail": "private-diagnostic-value"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(adapter), **kwargs),
    )
    with caplog.at_level(logging.WARNING):
        response = await harness.client.post(
            "/chat", json={"patient_key": "p_101", "question": "Summarize the latest note"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True
    assert body["policy_reason"] == "nemoclaw_unavailable"
    assert "NemoClaw sandbox setup failed" in body["retrievalSteps"]
    assert "sandbox setup failed" in caplog.text
    assert "503" in caplog.text
    assert "private-diagnostic-value" not in caplog.text


async def test_chat_allows_cold_sandbox_startup_before_running_agent(harness, monkeypatch):
    """A normal cold start can take minutes; it must not fall into the outage path."""
    harness.settings.openshell_url = "http://adapter.test"
    await harness.login("chen", auth_level=2)
    original_client = httpx.AsyncClient
    calls = []

    def adapter(request):
        calls.append(request.url.path)
        if request.url.path == "/v1/sandboxes":
            # Simulate a cold start exceeding the formerly hardcoded 20-second deadline.
            if request.extensions["timeout"]["read"] < 90:
                raise httpx.ReadTimeout("Cold sandbox is still starting", request=request)
            return httpx.Response(200, json={"sandbox_id": "p360-s-coldstart123"})
        if request.url.path == "/v1/credentials":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/turns":
            return httpx.Response(200, json={"answer": "Admission note reviewed [note_p101_admit]."})
        raise AssertionError(f"Unexpected adapter endpoint: {request.url.path}")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(adapter), **kwargs),
    )
    response = await harness.client.post(
        "/chat", json={"patient_key": "p_101", "question": "Summarize the latest note"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert "OpenShell sandbox turn" in body["retrievalSteps"]
    assert calls == ["/v1/sandboxes", "/v1/credentials", "/v1/turns"]
