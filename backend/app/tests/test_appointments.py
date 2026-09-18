"""Appointments: book / cancel / availability, and booked rows on the encounters dataset."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from patient360.errors import NOT_FOUND_BYTES

from .conftest import Harness


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_weekday_slot(*, hour: int = 9) -> datetime:
    day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.replace(hour=hour)


async def _login(c: httpx.AsyncClient, who: str, **kw) -> dict:
    r = await c.post("/auth/dev-login", json={"login": who, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def _query(c: httpx.AsyncClient, patient: str, dataset: str) -> httpx.Response:
    return await c.post("/tools/query", json={"patient_key": patient, "dataset": dataset})


async def test_maria_and_diego_book_and_see_via_encounters(harness: Harness):
    start = next_weekday_slot(hour=9)
    await harness.login("maria")
    booked = await harness.client.post(
        "/appointments",
        json={
            "patient_key": "p_103",
            "practitioner_user_id": "u_okafor",
            "start": _iso(start),
            "end": _iso(start + timedelta(minutes=30)),
            "dept": "cardiology",
        },
    )
    assert booked.status_code == 201, booked.text
    body = booked.json()
    assert body["status"] == "booked" and body["patient_key"] == "p_103"
    assert body["practitioner_user_id"] == "u_okafor" and body["created_by"] == "u_maria"
    assert harness.audit.of_type("appointment_booked")
    decision = harness.audit.of_type("decision")[-1]
    assert decision.reason_code == "self_match" and decision.detail["fga_consulted"] is False

    seen = await _query(harness.client, "p_103", "encounters")
    assert seen.status_code == 200
    assert any(
        row.get("status") == "booked" and row.get("dept") == "cardiology" for row in seen.json()["rows"]
    )

    async with harness.new_client() as diego:
        await _login(diego, "diego")
        later = next_weekday_slot(hour=14)
        r = await diego.post(
            "/appointments",
            json={
                "patient_key": "p_103",
                "practitioner_user_id": "u_okafor",
                "start": _iso(later),
                "dept": "cardiology",
            },
        )
        assert r.status_code == 201, r.text
        enc = await _query(diego, "p_103", "encounters")
        assert enc.status_code == 200
        assert sum(1 for row in enc.json()["rows"] if row.get("status") == "booked") >= 2


async def test_agent_cannot_book(harness: Harness):
    await harness.login("chen", auth_level=2)
    token = (await harness.client.post("/dev/run-token", json={})).json()["access_token"]
    r = await harness.client.post(
        "/appointments",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "patient_key": "p_101",
            "practitioner_user_id": "u_chen",
            "start": _iso(next_weekday_slot()),
        },
    )
    assert r.status_code == 401


async def test_chen_cannot_cancel_marias_booking(harness: Harness):
    start = next_weekday_slot(hour=14)
    await harness.login("maria")
    booked = await harness.client.post(
        "/appointments",
        json={
            "patient_key": "p_103",
            "practitioner_user_id": "u_okafor",
            "start": _iso(start),
        },
    )
    assert booked.status_code == 201, booked.text
    appointment_id = booked.json()["id"]

    async with harness.new_client() as chen:
        await _login(chen, "chen", auth_level=2)
        r = await chen.patch(f"/appointments/{appointment_id}", json={"status": "cancelled"})
        assert r.status_code == 404 and r.content == NOT_FOUND_BYTES


async def test_invalid_practitioner_is_422(harness: Harness):
    await harness.login("maria")
    r = await harness.client.post(
        "/appointments",
        json={
            "patient_key": "p_103",
            "practitioner_user_id": "u_nair",
            "start": _iso(next_weekday_slot()),
        },
    )
    assert r.status_code == 422
    assert r.json()["issue"][0]["details"]["coding"][0]["code"] == "practitioner_invalid"


async def test_availability_is_opaque_and_drops_booked_slots(harness: Harness):
    await harness.login("diego")
    before = await harness.client.post("/tools/availability", json={"practitioner_user_id": "u_okafor"})
    assert before.status_code == 200, before.text
    slots = before.json()["slots"]
    assert slots
    assert all("name" not in s and "display" not in s for s in slots)
    assert {s["practitioner_user_id"] for s in slots} == {"u_okafor"}

    chosen = datetime.fromisoformat(slots[0]["start"].replace("Z", "+00:00"))
    booked = await harness.client.post(
        "/appointments",
        json={
            "patient_key": "p_103",
            "practitioner_user_id": "u_okafor",
            "start": slots[0]["start"],
            "end": slots[0]["end"],
            "dept": "cardiology",
        },
    )
    assert booked.status_code == 201, booked.text

    after = await harness.client.post("/tools/availability", json={"practitioner_user_id": "u_okafor"})
    remaining = after.json()["slots"]
    assert not any(datetime.fromisoformat(s["start"].replace("Z", "+00:00")) == chosen for s in remaining)


async def test_cancel_is_idempotent_conflict_and_self_can_cancel(harness: Harness):
    await harness.login("maria")
    booked = await harness.client.post(
        "/appointments",
        json={
            "patient_key": "p_103",
            "practitioner_user_id": "u_okafor",
            "start": _iso(next_weekday_slot(hour=14)),
        },
    )
    appointment_id = booked.json()["id"]
    cancelled = await harness.client.patch(f"/appointments/{appointment_id}", json={"status": "cancelled"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert harness.audit.of_type("appointment_cancelled")

    again = await harness.client.patch(f"/appointments/{appointment_id}", json={"status": "cancelled"})
    assert again.status_code == 409
    assert again.json()["issue"][0]["details"]["coding"][0]["code"] == "already_cancelled"


async def test_nair_cannot_book(harness: Harness):
    await harness.login("nair")
    r = await harness.client.post(
        "/appointments",
        json={
            "patient_key": "p_101",
            "practitioner_user_id": "u_chen",
            "start": _iso(next_weekday_slot()),
        },
    )
    assert r.status_code == 404 and r.content == NOT_FOUND_BYTES
