"""OpenFGA relationship checks and tuple writes (Build Plan §4.2).

OpenFGA answers one question: does user:u_xxx hold relation R on
patient:p_xxx (or project:..., ward:...) at current_time? Every check carries
context.current_time because every grant is conditioned on active_window; a
conditioned tuple checked without it is an error on the server, and any error
here is a Transient (503), never a permit. The store is resolved by name at
startup and the newest authorization model is pinned so a decision can be
replayed against the exact model that made it (policy_version = fga:{model_id}).

Writes go through the same client. Only the human write endpoints (consent
grant, consent revoke, break-glass) call them, always after a PDP decision and
always paired with an audit row in the same handler.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from .errors import Transient

log = logging.getLogger(__name__)

CONDITION_NAME = "active_window"


def rfc3339(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("Context.now must be timezone-aware")
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Window:
    start: datetime
    expiry: datetime

    def is_live(self, now: datetime) -> bool:
        return self.start <= now < self.expiry


@dataclass(frozen=True, slots=True)
class Tuple:
    user: str
    relation: str
    object: str
    window: Window | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.user, self.relation, self.object)

    def to_key(self, *, with_condition: bool) -> dict[str, Any]:
        body: dict[str, Any] = {"user": self.user, "relation": self.relation, "object": self.object}
        if with_condition and self.window is not None:
            body["condition"] = {
                "name": CONDITION_NAME,
                "context": {"start": rfc3339(self.window.start), "expiry": rfc3339(self.window.expiry)},
            }
        return body

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"user": self.user, "relation": self.relation, "object": self.object}
        if self.window is not None:
            d["start"] = rfc3339(self.window.start)
            d["expiry"] = rfc3339(self.window.expiry)
        return d


class FgaUnavailable(Transient):
    """Transport, validation, or unexpected response from OpenFGA."""


class TupleExists(Exception):
    """A write named a tuple that already exists."""


class TupleMissing(Exception):
    """A delete named a tuple that does not exist."""


class RelationChecker(Protocol):
    policy_version: str

    async def check(self, user: str, relation: str, obj: str, now: datetime) -> bool: ...

    async def list_objects(self, user: str, relation: str, type_: str, now: datetime) -> list[str]: ...

    async def write(self, writes: Sequence[Tuple] = (), deletes: Sequence[Tuple] = ()) -> None: ...

    async def read(self, obj: str, relation: str | None = None, user: str | None = None) -> list[Tuple]: ...


class HttpFgaClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        store_name: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.store_name = store_name
        self.store_id: str | None = None
        self.model_id: str | None = None
        self.policy_version = "fga:unpinned"
        self._client = client or httpx.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def start(self) -> None:
        """Resolve the store by exact name (0 or >1 matches refuse to start) and pin the newest model."""
        ids: list[str] = []
        token: str | None = None
        while True:
            params: dict[str, str] = {"page_size": "100"}
            if token:
                params["continuation_token"] = token
            resp = await self._client.get("/stores", params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"openfga: list stores returned {resp.status_code}")
            body = resp.json()
            ids.extend(s["id"] for s in body.get("stores", []) if s.get("name") == self.store_name)
            token = body.get("continuation_token") or None
            if not token:
                break
        if len(ids) != 1:
            raise RuntimeError(f"openfga: {len(ids)} stores named {self.store_name!r}; refusing to start")
        self.store_id = ids[0]

        resp = await self._client.get(
            f"/stores/{self.store_id}/authorization-models", params={"page_size": "1"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"openfga: list models returned {resp.status_code}")
        models = resp.json().get("authorization_models", [])
        if not models:
            raise RuntimeError(f"openfga: store {self.store_id} has no authorization model")
        self.model_id = models[0]["id"]
        self.policy_version = f"fga:{self.model_id}"
        log.info("openfga store=%s model=%s", self.store_id, self.model_id)

    async def check(self, user: str, relation: str, obj: str, now: datetime) -> bool:
        body = {
            "tuple_key": {"user": user, "relation": relation, "object": obj},
            "authorization_model_id": self.model_id,
            "context": {"current_time": rfc3339(now)},
        }
        try:
            resp = await self._client.post(f"/stores/{self.store_id}/check", json=body)
        except httpx.HTTPError as exc:
            log.error("openfga check transport error: %s", exc.__class__.__name__)
            raise FgaUnavailable("openfga unreachable") from exc
        if resp.status_code != 200:
            log.error("openfga check returned %s", resp.status_code)
            raise FgaUnavailable(f"openfga check {resp.status_code}")
        return bool(resp.json().get("allowed", False))

    async def list_objects(self, user: str, relation: str, type_: str, now: datetime) -> list[str]:
        body = {
            "type": type_,
            "relation": relation,
            "user": user,
            "authorization_model_id": self.model_id,
            "context": {"current_time": rfc3339(now)},
        }
        try:
            resp = await self._client.post(f"/stores/{self.store_id}/list-objects", json=body)
        except httpx.HTTPError as exc:
            log.error("openfga list-objects transport error: %s", exc.__class__.__name__)
            raise FgaUnavailable("openfga unreachable") from exc
        if resp.status_code != 200:
            log.error("openfga list-objects returned %s", resp.status_code)
            raise FgaUnavailable(f"openfga list-objects {resp.status_code}")
        return list(resp.json().get("objects", []))

    async def write(self, writes: Sequence[Tuple] = (), deletes: Sequence[Tuple] = ()) -> None:
        """One atomic Write call. Conditioned tuples carry active_window; deletes never carry a condition."""
        if not writes and not deletes:
            return
        body: dict[str, Any] = {"authorization_model_id": self.model_id}
        if writes:
            body["writes"] = {"tuple_keys": [t.to_key(with_condition=True) for t in writes]}
        if deletes:
            body["deletes"] = {"tuple_keys": [t.to_key(with_condition=False) for t in deletes]}
        try:
            resp = await self._client.post(f"/stores/{self.store_id}/write", json=body)
        except httpx.HTTPError as exc:
            log.error("openfga write transport error: %s", exc.__class__.__name__)
            raise FgaUnavailable("openfga unreachable") from exc
        if resp.status_code == 200:
            return
        if resp.status_code == 400:
            # v1.8 reports both cases with one code; the request shape tells them apart.
            code = (
                (resp.json() or {}).get("code")
                if resp.headers.get("content-type", "").startswith("application/json")
                else None
            )
            if code == "write_failed_due_to_invalid_input":
                if writes and not deletes:
                    raise TupleExists("tuple already exists")
                if deletes and not writes:
                    raise TupleMissing("tuple does not exist")
        log.error("openfga write returned %s", resp.status_code)
        raise FgaUnavailable(f"openfga write {resp.status_code}")

    async def read(self, obj: str, relation: str | None = None, user: str | None = None) -> list[Tuple]:
        """Tuples on one object (optionally one relation or one user). Follows pagination."""
        key: dict[str, str] = {"object": obj}
        if relation:
            key["relation"] = relation
        if user:
            key["user"] = user
        out: list[Tuple] = []
        token: str | None = None
        while True:
            body: dict[str, Any] = {"tuple_key": key, "page_size": 100}
            if token:
                body["continuation_token"] = token
            try:
                resp = await self._client.post(f"/stores/{self.store_id}/read", json=body)
            except httpx.HTTPError as exc:
                log.error("openfga read transport error: %s", exc.__class__.__name__)
                raise FgaUnavailable("openfga unreachable") from exc
            if resp.status_code != 200:
                log.error("openfga read returned %s", resp.status_code)
                raise FgaUnavailable(f"openfga read {resp.status_code}")
            data = resp.json()
            for item in data.get("tuples", []):
                k = item.get("key", {})
                window = None
                cond = k.get("condition") or {}
                ctx = cond.get("context") or {}
                if cond.get("name") == CONDITION_NAME and "start" in ctx and "expiry" in ctx:
                    window = Window(parse_rfc3339(ctx["start"]), parse_rfc3339(ctx["expiry"]))
                out.append(Tuple(k["user"], k["relation"], k["object"], window))
            token = data.get("continuation_token") or None
            if not token:
                break
        return out
