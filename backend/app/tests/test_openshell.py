from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from patient360.openshell import (
    _agent_text,
    destroy_session_sandbox,
    is_protected_sandbox,
    register_run_token,
    sandbox_turn,
    session_sandbox_name,
    try_openshell_turn,
)

from .conftest import make_settings


def test_agent_text_reads_nemoclaw_payloads():
    body = {
        "status": "ok",
        "result": {"payloads": [{"text": "ready"}], "meta": {"finalAssistantVisibleText": "ready"}},
    }
    assert _agent_text(body) == "ready"


def test_session_sandbox_name_is_sid_bound():
    sid = "ab" * 32
    assert session_sandbox_name(sid) == f"p360-s-{sid[:12]}"
    assert is_protected_sandbox("patient360")
    assert is_protected_sandbox("main")
    assert not is_protected_sandbox("p360-s-abcdef123456")


async def test_openshell_runs_even_if_runtime_label_is_inproc():
    settings = make_settings(agent_runtime="inproc", openshell_url="http://openshell.test")
    with (
        patch("patient360.openshell.register_run_token", new=AsyncMock(return_value=True)),
        patch("patient360.openshell.sandbox_turn", new=AsyncMock(return_value="ok")),
    ):
        assert await try_openshell_turn(settings, "tok", "q", sandbox="p360-s-test") == "ok"


async def test_openshell_falls_back_when_http_fails():
    settings = make_settings(agent_runtime="openshell", openshell_url="http://openshell.test")
    with (
        patch("patient360.openshell.register_run_token", new=AsyncMock(side_effect=RuntimeError("down"))),
        patch("patient360.openshell.sandbox_turn", new=AsyncMock(side_effect=RuntimeError("down"))),
    ):
        assert await try_openshell_turn(settings, "tok", "q", sandbox="p360-s-test") is None


async def test_openshell_uses_host_adapter_turn():
    settings = make_settings(agent_runtime="openshell", openshell_url="http://openshell.test")
    with (
        patch("patient360.openshell.register_run_token", new=AsyncMock(return_value=True)) as register,
        patch("patient360.openshell.sandbox_turn", new=AsyncMock(return_value="HbA1c is 6.98% [obs_x].")) as turn,
    ):
        text = await try_openshell_turn(
            settings, "tok", "q", sandbox="p360-s-test", patient_key="p_101"
        )
    assert "6.98" in (text or "")
    register.assert_awaited_once()
    assert register.await_args.kwargs["sandbox"] == "p360-s-test"
    assert turn.await_args.kwargs["patient_key"] == "p_101"
    assert turn.await_args.kwargs["sandbox"] == "p360-s-test"


async def test_openshell_skipped_when_url_missing():
    settings = make_settings(agent_runtime="openshell", openshell_url="")
    assert await try_openshell_turn(settings, "tok", "q", sandbox="p360-s-test") is None


async def test_openshell_skips_gold_sandbox():
    settings = make_settings(agent_runtime="openshell", openshell_url="http://openshell.test")
    with patch("patient360.openshell.register_run_token", new=AsyncMock()) as register:
        assert await try_openshell_turn(settings, "tok", "q", sandbox="patient360") is None
    register.assert_not_called()


class _FakeResp:
    def __init__(self, status_code: int = 200, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._body


class _FakeClient:
    posts: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url: str, json: dict | None = None):
        self.posts.append((url, json or {}))
        if url.endswith("/v1/credentials"):
            return _FakeResp(200)
        return _FakeResp(200, {"answer": "ok"})

    async def delete(self, url: str):
        return _FakeResp(202)


async def test_register_and_turn_omit_evidence():
    _FakeClient.posts = []
    with patch("patient360.openshell.httpx.AsyncClient", _FakeClient):
        assert await register_run_token("http://openshell.test", "jwt", sandbox="p360-s-aa")
        text = await sandbox_turn(
            "http://openshell.test", "summarize note", sandbox="p360-s-aa", patient_key="p_101"
        )
    assert text == "ok"
    creds = _FakeClient.posts[0][1]
    turn = _FakeClient.posts[1][1]
    assert creds["sandbox"] == "p360-s-aa"
    assert creds["value"] == "jwt"
    assert turn["sandbox"] == "p360-s-aa"
    assert turn["patient_key"] == "p_101"
    assert "context" not in turn and "evidence" not in turn


async def test_destroy_skips_gold_and_empty_url():
    settings = make_settings(agent_runtime="openshell", openshell_url="")
    assert await destroy_session_sandbox(settings, "p360-s-aa") is False
    settings = make_settings(agent_runtime="openshell", openshell_url="http://openshell.test")
    assert await destroy_session_sandbox(settings, "patient360") is False


async def test_destroy_calls_adapter():
    settings = make_settings(agent_runtime="openshell", openshell_url="http://openshell.test")
    with patch("patient360.openshell.httpx.AsyncClient", _FakeClient):
        assert await destroy_session_sandbox(settings, "p360-s-aa") is True


def test_session_sandbox_name_rejects_short_sid():
    with pytest.raises(ValueError):
        session_sandbox_name("abc")
