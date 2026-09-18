"""HttpFgaClient against a mock OpenFGA: request shapes, model pinning, error mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from patient360.fga import FgaUnavailable, HttpFgaClient, Tuple, TupleExists, TupleMissing, Window

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


class MockFga:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []
        self.tuples: list[dict] = []
        self.stores = [{"id": "01STORE", "name": "patient360-grants"}]

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.requests.append((path, body))
        if path == "/stores":
            return httpx.Response(200, json={"stores": self.stores, "continuation_token": ""})
        if path.endswith("/authorization-models"):
            return httpx.Response(200, json={"authorization_models": [{"id": "01MODEL"}, {"id": "00OLD"}]})
        if path.endswith("/check"):
            key = body["tuple_key"]
            return httpx.Response(200, json={"allowed": key["user"] == "user:u_chen"})
        if path.endswith("/write"):
            existing = {(t["user"], t["relation"], t["object"]) for t in self.tuples}
            for k in body.get("writes", {}).get("tuple_keys", []):
                if (k["user"], k["relation"], k["object"]) in existing:
                    return httpx.Response(
                        400,
                        json={"code": "write_failed_due_to_invalid_input", "message": "already existed"},
                    )
            for k in body.get("deletes", {}).get("tuple_keys", []):
                if (k["user"], k["relation"], k["object"]) not in existing:
                    return httpx.Response(
                        400,
                        json={"code": "write_failed_due_to_invalid_input", "message": "did not exist"},
                    )
            dels = {
                (k["user"], k["relation"], k["object"]) for k in body.get("deletes", {}).get("tuple_keys", [])
            }
            self.tuples = [t for t in self.tuples if (t["user"], t["relation"], t["object"]) not in dels]
            self.tuples.extend(body.get("writes", {}).get("tuple_keys", []))
            return httpx.Response(200, json={})
        if path.endswith("/read"):
            key = body["tuple_key"]
            out = [
                {"key": t, "timestamp": "2026-09-18T12:00:00Z"}
                for t in self.tuples
                if t["object"] == key["object"]
                and ("relation" not in key or t["relation"] == key["relation"])
            ]
            return httpx.Response(200, json={"tuples": out, "continuation_token": ""})
        return httpx.Response(404)


@pytest.fixture
async def client():
    mock = MockFga()
    http = httpx.AsyncClient(transport=httpx.MockTransport(mock.handler), base_url="http://fga")
    fga = HttpFgaClient("http://fga", "key", "patient360-grants", client=http)
    await fga.start()
    yield fga, mock
    await fga.close()


async def test_start_pins_newest_model(client):
    fga, _ = client
    assert fga.store_id == "01STORE" and fga.model_id == "01MODEL"
    assert fga.policy_version == "fga:01MODEL"


async def test_start_refuses_ambiguous_store():
    mock = MockFga()
    mock.stores.append({"id": "02STORE", "name": "patient360-grants"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(mock.handler), base_url="http://fga")
    with pytest.raises(RuntimeError):
        await HttpFgaClient("http://fga", "key", "patient360-grants", client=http).start()


async def test_check_sends_model_and_current_time(client):
    fga, mock = client
    assert await fga.check("user:u_chen", "can_read_clinical", "patient:p_101", NOW) is True
    assert await fga.check("user:u_nair", "can_read_clinical", "patient:p_101", NOW) is False
    path, body = mock.requests[-1]
    assert path == "/stores/01STORE/check"
    assert body["authorization_model_id"] == "01MODEL"
    assert body["context"] == {"current_time": "2026-09-18T12:00:00Z"}


async def test_write_conditioned_tuple_then_read_then_delete(client):
    fga, mock = client
    win = Window(NOW, datetime(2026, 9, 18, 13, 0, tzinfo=UTC))
    t = Tuple("user:u_chen", "emergency", "patient:p_205", win)
    await fga.write(writes=[t])
    _, body = mock.requests[-1]
    assert body["writes"]["tuple_keys"] == [
        {
            "user": "user:u_chen",
            "relation": "emergency",
            "object": "patient:p_205",
            "condition": {
                "name": "active_window",
                "context": {"start": "2026-09-18T12:00:00Z", "expiry": "2026-09-18T13:00:00Z"},
            },
        }
    ]
    assert "deletes" not in body

    got = await fga.read("patient:p_205")
    assert got == [t]

    await fga.write(deletes=[t])
    _, body = mock.requests[-1]
    assert body["deletes"]["tuple_keys"] == [
        {"user": "user:u_chen", "relation": "emergency", "object": "patient:p_205"}
    ]  # deletes never carry a condition
    assert await fga.read("patient:p_205") == []


async def test_duplicate_write_and_missing_delete_are_typed(client):
    fga, _ = client
    t = Tuple("user:u_diego", "caregiver", "patient:p_103", Window(NOW, datetime(2027, 1, 1, tzinfo=UTC)))
    await fga.write(writes=[t])
    with pytest.raises(TupleExists):
        await fga.write(writes=[t])
    await fga.write(deletes=[t])
    with pytest.raises(TupleMissing):
        await fga.write(deletes=[t])


async def test_other_errors_are_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/stores":
            return httpx.Response(200, json={"stores": [{"id": "S", "name": "patient360-grants"}]})
        if request.url.path.endswith("/authorization-models"):
            return httpx.Response(200, json={"authorization_models": [{"id": "M"}]})
        return httpx.Response(500)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fga")
    fga = HttpFgaClient("http://fga", "key", "patient360-grants", client=http)
    await fga.start()
    with pytest.raises(FgaUnavailable):
        await fga.check("user:u_chen", "can_read_clinical", "patient:p_101", NOW)
    with pytest.raises(FgaUnavailable):
        await fga.write(writes=[Tuple("user:u_chen", "emergency", "patient:p_205")])
    with pytest.raises(FgaUnavailable):
        await fga.read("patient:p_205")
