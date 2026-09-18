"""Against live Postgres + OpenFGA (+ optional OpenBao). Skipped unless PATIENT360_DB_DSN is set.

On the server, after `compose up` and `seed_demo.py`:

    cd backend/app
    PATIENT360_DB_DSN=postgres://p360_app:$PATIENT360_APP_PASSWORD@127.0.0.1:5432/fhir \
    PATIENT360_OPENFGA_URL=http://127.0.0.1:8091 PATIENT360_OPENFGA_KEY=$PATIENT360_OPENFGA_KEY \
    PATIENT360_LINKAGE_URL=http://127.0.0.1:8200 PATIENT360_LINKAGE_TOKEN=$PATIENT360_LINKAGE_BACKEND_TOKEN \
    uv run pytest -m integration -q

Only date-stable personas are used (Chen's window runs to 2027; Rivera's one-week window and
Okafor's demo-relative window are rewritten by seed_grants.py, Track B).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

from patient360.config import Settings
from patient360.deps import build_deps
from patient360.errors import NOT_FOUND_BYTES
from patient360.main import create_app

pytestmark = pytest.mark.integration

DSN = os.environ.get("PATIENT360_DB_DSN")
skip = pytest.mark.skipif(not DSN, reason="PATIENT360_DB_DSN not set")


@pytest.fixture
async def live() -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        db_dsn=DSN,
        openfga_url=os.environ.get("PATIENT360_OPENFGA_URL", "http://127.0.0.1:8091"),
        openfga_key=os.environ.get("PATIENT360_OPENFGA_KEY", "patient360-openfga-dev"),
        linkage_url=os.environ.get("PATIENT360_LINKAGE_URL", "http://127.0.0.1:8200"),
        linkage_token=os.environ.get("PATIENT360_LINKAGE_TOKEN", "patient360-linkage-dev"),
        run_token_secret=os.environ.get(
            "PATIENT360_RUN_TOKEN_SECRET", "integration-run-token-secret-0123456789"
        ),
        dev=True,
        cookie_secure=False,
    )
    deps = await build_deps(settings)
    app = create_app(settings, deps)
    app.state.deps = deps
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        await deps.close()


async def _login(c: httpx.AsyncClient, login: str, **kw) -> dict:
    r = await c.post("/auth/dev-login", json={"login": login, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def _q(c: httpx.AsyncClient, patient: str, dataset: str) -> httpx.Response:
    return await c.post("/tools/query", json={"patient_key": patient, "dataset": dataset})


@skip
async def test_policy_version_is_pinned_from_openfga(live):
    r = await live.get("/healthz")
    assert r.status_code == 200
    assert r.json()["policy_version"].startswith("fga:") and r.json()["policy_version"] != "fga:unpinned"


@skip
async def test_chen_reads_p101_and_gets_uniform_404_elsewhere(live):
    await _login(live, "chen", auth_level=2)
    r = await _q(live, "p_101", "labs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count"] > 0 and body["decision"]["relation"] == "can_read_clinical"
    r1 = await _q(live, "p_205", "labs")
    r2 = await _q(live, "p_999", "labs")
    assert r1.status_code == r2.status_code == 404
    assert r1.content == r2.content == NOT_FOUND_BYTES
    audit = await live.get(f"/audit/{body['audit_id']}")
    assert audit.status_code == 200 and audit.json()["policy_version"] == body["decision"]["policy_version"]


@skip
async def test_researcher_and_patient_paths(live):
    await _login(live, "nair")
    assert (await _q(live, "p_101", "labs")).status_code == 404
    me = await _login(live, "maria")
    assert me["self_patient_id"] == "p_103", "vault link u_maria -> p_103 missing (run seed_demo.py)"
    assert (await _q(live, "p_101", "labs")).status_code == 404
    r = await _q(live, "p_103", "meds")
    assert r.status_code == 200 and r.json()["decision"]["reason_code"] == "self_match"


@skip
async def test_off_duty_and_run_token_lifecycle(live):
    await _login(live, "chen", on_duty=False)
    r = await _q(live, "p_101", "labs")
    assert r.status_code == 403
    await _login(live, "chen", auth_level=2)
    token = (await live.post("/dev/run-token", json={})).json()["access_token"]
    async with httpx.AsyncClient(transport=live._transport, base_url="http://test") as agent:
        r = await agent.post(
            "/tools/query",
            json={"patient_key": "p_101", "dataset": "labs"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert (await live.post("/auth/logout")).status_code == 204
        r = await agent.post(
            "/tools/query",
            json={"patient_key": "p_101", "dataset": "labs"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
