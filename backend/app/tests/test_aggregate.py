"""Aggregate / k-min path: researcher project, attending own-cohort, dietary ward, overlap."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from patient360.errors import NOT_FOUND_BYTES
from patient360.main import create_app
from patient360.pdp import Context, Resource, evaluate
from patient360.tools.aggregate import apply_suppression

from .conftest import Harness, make_deps, make_settings
from .fakes import FakeClinical, FakeFga, aggregate_cohort_rows, complementary_leak_rows
from .test_pdp_matrix import subject

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _agg_ctx(**kw):
    base = dict(
        now=NOW,
        channel="dashboard",
        purpose="HRESCH",
        action="read",
        group_by=("code",),
        project_id="cohort_2026",
        k_min=5,
        allowed_dims=("code", "sex", "birth_year", "clinical_status", "category"),
    )
    base.update(kw)
    return Context(**base)  # type: ignore[arg-type]


def _agg_resource(dataset: str = "conditions") -> Resource:
    return Resource(type="aggregate", dataset=dataset)


async def test_nair_project_permit_and_suppression(harness: Harness):
    harness.clinical.rows = aggregate_cohort_rows()
    await harness.login("nair")
    r = await harness.client.post(
        "/tools/query",
        json={
            "dataset": "conditions",
            "aggregate": {"group_by": ["code"], "project_id": "cohort_2026"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_code = {c["dims"]["code"]: c for c in body["rows"]}
    assert by_code["44054006"]["count"] == 12 and by_code["44054006"]["suppressed"] is False
    assert by_code["44054006"]["display"] == "Type 2 diabetes"
    assert by_code["195967001"]["count"] == 6 and by_code["195967001"]["suppressed"] is False
    assert by_code["195967001"]["display"] == "Asthma"
    assert by_code["22298006"]["suppressed"] is True and by_code["22298006"]["count"] is None
    assert by_code["22298006"]["display"] == "Myocardial infarction"
    assert by_code["386661006"]["suppressed"] is True and by_code["386661006"]["count"] is None
    assert body["suppressed_cells"] == 2
    assert body["obligations"]["k_min"] == 5
    assert body["patient_key"] is None
    assert harness.audit.aggregates[-1]["dataset"] == "conditions"


async def test_complementary_suppresses_lone_sibling():
    cells = apply_suppression(
        [{"code": "44054006", "count": 12}, {"code": "386661006", "count": 3}],
        ["code"],
        5,
    )
    assert all(c["suppressed"] and c["count"] is None for c in cells)


def test_display_survives_k_min_blanking():
    cells = apply_suppression(
        [{"code": "386661006", "display": "Fever", "count": 3}],
        ["code"],
        5,
    )
    assert cells[0]["suppressed"] is True
    assert cells[0]["count"] is None
    assert cells[0]["display"] == "Fever"
    assert cells[0]["dims"] == {"code": "386661006"}


async def test_nair_without_project_or_bad_dim_is_404(harness: Harness):
    await harness.login("nair")
    cases = [
        {"dataset": "conditions", "aggregate": {"group_by": ["code"]}},
        {"dataset": "conditions", "aggregate": {"group_by": ["code"], "project_id": "no_such"}},
        {
            "dataset": "conditions",
            "aggregate": {"group_by": ["effective_at"], "project_id": "cohort_2026"},
        },
        {
            "dataset": "conditions",
            "aggregate": {"group_by": ["patient_key"], "project_id": "cohort_2026"},
        },
    ]
    for body in cases:
        r = await harness.client.post("/tools/query", json=body)
        assert r.status_code == 404 and r.content == NOT_FOUND_BYTES, body


async def test_nair_per_patient_still_404(harness: Harness):
    await harness.login("nair")
    r = await harness.client.post("/tools/query", json={"patient_key": "p_101", "dataset": "labs"})
    assert r.status_code == 404 and r.content == NOT_FOUND_BYTES
    assert harness.audit.of_type("decision")[-1].reason_code == "aggregate_only"


async def test_overlap_blocks_second_query(harness: Harness):
    harness.clinical.rows = aggregate_cohort_rows()
    await harness.login("nair")
    first = await harness.client.post(
        "/tools/query",
        json={
            "dataset": "conditions",
            "aggregate": {"group_by": ["code"], "project_id": "cohort_2026"},
        },
    )
    assert first.status_code == 200
    logged = len(harness.audit.aggregates)
    second = await harness.client.post(
        "/tools/query",
        json={
            "dataset": "conditions",
            "filters": {"code": "44054006"},
            "aggregate": {"group_by": ["code"], "project_id": "cohort_2026"},
        },
    )
    assert second.status_code == 404 and second.content == NOT_FOUND_BYTES
    assert harness.audit.of_type("decision")[-1].reason_code == "overlap_blocked"
    assert len(harness.audit.aggregates) == logged


async def test_chen_own_cohort_no_k_min(harness: Harness):
    await harness.login("chen", auth_level=2)
    r = await harness.client.post(
        "/tools/query", json={"dataset": "conditions", "aggregate": {"group_by": ["code"]}}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "k_min" not in body["obligations"]
    assert harness.clinical.aggregate_log[-1]["scoped_keys"] == ("p_101", "p_102")


async def test_others_cannot_aggregate(harness: Harness):
    for who in ("maria", "rivera", "haller"):
        async with harness.new_client() as c:
            await c.post("/auth/dev-login", json={"login": who, "auth_level": 2})
            r = await c.post(
                "/tools/query", json={"dataset": "conditions", "aggregate": {"group_by": ["code"]}}
            )
            assert r.status_code == 404 and r.content == NOT_FOUND_BYTES, who


async def test_lindqvist_ward_diet_not_labs(harness: Harness):
    await harness.login("lindqvist")
    diet = await harness.client.post(
        "/tools/query", json={"dataset": "diet", "aggregate": {"group_by": ["ward"]}}
    )
    assert diet.status_code == 200, diet.text
    assert diet.json()["rows"]
    labs = await harness.client.post(
        "/tools/query", json={"dataset": "labs", "aggregate": {"group_by": ["code"]}}
    )
    assert labs.status_code == 404 and labs.content == NOT_FOUND_BYTES


async def test_agent_channel_aggregate_allowed(harness: Harness):
    harness.clinical.rows = aggregate_cohort_rows()
    await harness.login("nair")
    token = (await harness.client.post("/dev/run-token", json={"agent_id": "agent:dev"})).json()[
        "access_token"
    ]
    r = await harness.client.post(
        "/tools/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "dataset": "conditions",
            "aggregate": {"group_by": ["code"], "project_id": "cohort_2026"},
        },
    )
    assert r.status_code == 200, r.text


async def test_pdp_aggregate_matrix():
    fga = FakeFga()
    nair = subject("u_nair")
    d = await evaluate(nair, _agg_resource(), _agg_ctx(), fga.check, list_objects=fga.list_objects)
    assert d.effect == "permit" and d.reason_code == "aggregate_project" and d.obligations.k_min == 5

    d = await evaluate(nair, _agg_resource(), _agg_ctx(project_id=None), fga.check)
    assert d.effect == "not_found" and d.reason_code == "aggregate_project_missing"

    chen = subject("u_chen")
    d = await evaluate(
        chen,
        _agg_resource(),
        _agg_ctx(purpose="TREAT", project_id=None, k_min=None),
        fga.check,
        list_objects=fga.list_objects,
    )
    assert d.effect == "permit" and d.scoped_keys == ("p_101", "p_102")
    assert d.obligations.k_min is None

    maria = subject("u_maria", self_patient_id="p_103")
    d = await evaluate(maria, _agg_resource(), _agg_ctx(project_id=None), fga.check)
    assert d.effect == "not_found" and d.reason_code == "aggregate_role_not_allowed"


async def test_complementary_endpoint(harness: Harness):
    settings = make_settings()
    clinical = FakeClinical(complementary_leak_rows())
    deps, audit, fga, sessions, _ = make_deps(settings, clinical=clinical)
    app = create_app(settings, deps)
    app.state.deps = deps
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/dev-login", json={"login": "nair"})
        r = await c.post(
            "/tools/query",
            json={
                "dataset": "conditions",
                "aggregate": {"group_by": ["code"], "project_id": "cohort_2026"},
            },
        )
    assert r.status_code == 200
    assert all(cell["suppressed"] for cell in r.json()["rows"])
    assert r.json()["suppressed_cells"] == 2
