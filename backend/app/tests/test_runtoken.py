"""Run tokens: mint/verify unit cases (the OWASP LLM06 scoreboard rows) and the agent channel end to end."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from patient360.auth import runtoken
from patient360.errors import Unauthenticated

from .conftest import Harness, make_settings

SID = "ab" * 32
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _raw(settings, **over):
    payload = {
        "iss": settings.run_token_issuer,
        "sub": "user:u_chen",
        "act": {"sub": "agent:sbx_01"},
        "aud": settings.run_token_audience,
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=10)).timestamp()),
        "jti": "j1",
        "sid": SID,
    }
    headers = {"typ": over.pop("typ", "at+JWT")}
    secret = over.pop("secret", settings.run_token_secret.get_secret_value())
    for k, v in over.items():
        if v is None:
            payload.pop(k, None)
        else:
            payload[k] = v
    return jwt.encode(payload, secret, algorithm="HS256", headers=headers)


def test_mint_then_verify_roundtrip():
    s = make_settings()
    token, claims = runtoken.mint(s, user_id="u_chen", sid=SID, agent_id="agent:sbx_01", now=NOW)
    assert jwt.get_unverified_header(token)["typ"] == "at+JWT"
    got = runtoken.verify(s, token, now=NOW + timedelta(minutes=9))
    assert (
        got.user_id == "u_chen" and got.act_sub == "agent:sbx_01" and got.sid == SID and got.jti == claims.jti
    )
    assert got.exp - got.iat == timedelta(seconds=s.run_token_ttl_seconds)


@pytest.mark.parametrize(
    "case,over",
    [
        ("forged signature", {"secret": "wrong-secret-that-is-long-enough-0123456789"}),
        ("wrong aud", {"aud": "patient360-dashboard"}),
        ("wrong iss", {"iss": "someone-else"}),
        ("missing act", {"act": None}),
        ("act without sub", {"act": {"role": "agent"}}),
        ("wrong typ", {"typ": "JWT"}),
        ("missing jti", {"jti": None}),
        ("missing sid", {"sid": None}),
        ("short sid", {"sid": "abcd"}),
        ("sub not a user", {"sub": "agent:sbx_01"}),
        ("missing exp", {"exp": None}),
    ],
)
def test_rejections(case, over):
    s = make_settings()
    with pytest.raises(Unauthenticated):
        runtoken.verify(s, _raw(s, **over), now=NOW)


def test_expired_token_rejected():
    s = make_settings()
    token = _raw(s)
    with pytest.raises(Unauthenticated):
        runtoken.verify(s, token, now=NOW + timedelta(minutes=11))


def test_garbage_rejected():
    with pytest.raises(Unauthenticated):
        runtoken.verify(make_settings(), "not.a.jwt", now=NOW)


async def test_agent_channel_end_to_end(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post("/dev/run-token", json={"agent_id": "agent:sbx_01"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    async with harness.new_client() as agent:  # no cookie, only the bearer
        r = await agent.post(
            "/tools/query",
            json={"patient_key": "p_101", "dataset": "labs"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["row_count"] == 2
        # dashboard-only endpoints refuse the run token (aud wall)
        r = await agent.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        r = await agent.post("/dev/run-token", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    decision = harness.audit.of_type("decision")[-1]
    assert decision.detail["channel"] == "agent"
    assert decision.agent_software == "agent:sbx_01"
    assert decision.jti


async def test_logout_revokes_outstanding_run_tokens(harness: Harness):
    await harness.login("chen", auth_level=2)
    token = (await harness.client.post("/dev/run-token", json={})).json()["access_token"]
    r = await harness.client.post("/auth/logout")
    assert r.status_code == 204
    async with harness.new_client() as agent:
        r = await agent.post(
            "/tools/query",
            json={"patient_key": "p_101", "dataset": "labs"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401


async def test_tampered_and_foreign_tokens_are_401(harness: Harness):
    await harness.login("chen", auth_level=2)
    token = (await harness.client.post("/dev/run-token", json={})).json()["access_token"]
    head, body, sig = token.split(".")
    tampered = f"{head}.{body}.{sig[:-2]}xx"
    async with harness.new_client() as agent:
        for bad in (tampered, "Bearer", ""):
            r = await agent.post(
                "/tools/query",
                json={"patient_key": "p_101", "dataset": "labs"},
                headers={"Authorization": f"Bearer {bad}"},
            )
            assert r.status_code == 401
    assert harness.audit.of_type("decision") == []


async def test_dev_endpoints_hidden_when_dev_is_off():
    import httpx

    from patient360.main import create_app

    from .conftest import make_deps

    settings = make_settings(dev=False)
    deps, *_ = make_deps(settings)
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/dev-login", json={"login": "chen"})
        assert (await c.post("/dev/run-token", json={})).status_code == 404
        assert (await c.get("/auth/dev-personas")).status_code == 404
        assert (await c.get("/docs")).status_code == 404
