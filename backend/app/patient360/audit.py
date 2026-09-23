"""Audit writer: one row per PDP decision, tool call, login, logout, identity resolve.

Rows go to audit.audit_events (04-audit.sql). The BEFORE INSERT trigger draws
seq and computes the hash chain under an advisory lock that is held to commit,
so every insert here runs in its own autocommit statement and never inside a
longer transaction. A failed insert is a Transient (503): access never happens
without a record.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import Database
from .errors import Transient

log = logging.getLogger(__name__)

# audit.vs_event_type()
EVENT_TYPES = frozenset(
    {
        "decision",
        "tool_call",
        "consent_granted",
        "consent_revoked",
        "break_glass",
        "login",
        "logout",
        "step_up",
        "media_sign",
        "media_fetch",
        "ingest",
        "upload",
        "identity_resolve",
        "appointment_booked",
        "appointment_cancelled",
        "vista_reprocess",
    }
)
# audit.vs_purpose_of_use()
PURPOSES = frozenset({"TREAT", "HRESCH", "BTG", "PATRQT", "HOPERAT"})
# audit.vs_outcome(): 0 success, 4 minor failure, 8 serious failure, 12 major failure
OUTCOME_SUCCESS = "0"
OUTCOME_MINOR = "4"
OUTCOME_SERIOUS = "8"


@dataclass(slots=True)
class AuditEvent:
    event_type: str
    outcome: str = OUTCOME_SUCCESS
    agent_user: str | None = None
    agent_software: str | None = None
    purpose_of_event: str | None = None
    entity_patient: str | None = None
    entity_resource: str | None = None
    entity_query: str | None = None
    outcome_desc: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    reason_code: str | None = None
    session_id: str | None = None
    jti: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def encode_query(params: Any) -> str:
    """entity_query: base64 of the tool parameters as received (canonical JSON)."""
    raw = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return base64.b64encode(raw).decode("ascii")


class AuditWriter(Protocol):
    async def write(self, event: AuditEvent) -> UUID: ...


class AuditReader(Protocol):
    async def get(self, audit_id: UUID) -> dict[str, Any] | None: ...

    async def get_consent(self, consent_id: UUID) -> dict[str, Any] | None:
        """The consent_granted row that *is* the consent record, or None."""
        ...

    async def consent_events(self, patient_key: str) -> list[dict[str, Any]]:
        """consent_granted and consent_revoked rows for one patient, chain order."""
        ...

    async def active_break_glass(
        self, user_id: str, patient_key: str, now: datetime
    ) -> dict[str, Any] | None:
        """The newest break_glass row by this user on this patient whose window is still open."""
        ...

    async def log_aggregate(
        self,
        *,
        session_id: str | None,
        user_id: str,
        dataset: str,
        group_by: list[str],
        filters: dict[str, Any],
        cells: list[dict[str, Any]],
        suppressed_cells: int,
        k_min: int | None,
        audit_id: UUID | None,
    ) -> None:
        """Record an answered aggregate query for overlap detection."""
        ...

    async def session_aggregates(self, session_id: str) -> list[dict[str, Any]]:
        """Prior answered aggregates for this session, oldest first."""
        ...

    async def list_events(self, *, limit: int = 100, agent_user: str | None = None) -> list[dict[str, Any]]:
        """Newest audit rows. agent_user=None is the auditor feed."""
        ...


_INSERT = """
INSERT INTO audit.audit_events (
    event_type, agent_user, agent_software, purpose_of_event,
    entity_patient, entity_resource, entity_query,
    outcome, outcome_desc, policy_id, policy_version, reason_code,
    session_id, jti, detail
) VALUES (
    %(event_type)s, %(agent_user)s, %(agent_software)s, %(purpose_of_event)s,
    %(entity_patient)s, %(entity_resource)s, %(entity_query)s,
    %(outcome)s, %(outcome_desc)s, %(policy_id)s, %(policy_version)s, %(reason_code)s,
    %(session_id)s, %(jti)s, %(detail)s
)
RETURNING id
"""

_COLUMNS = """
SELECT seq, id, recorded_at, event_type, agent_user, agent_software, purpose_of_event,
       entity_patient, entity_resource, entity_query, outcome, outcome_desc,
       policy_id, policy_version, reason_code, session_id, jti, detail,
       encode(prev_hash, 'hex') AS prev_hash, encode(row_hash, 'hex') AS row_hash
FROM audit.audit_events
"""

_SELECT = _COLUMNS + "WHERE id = %(id)s"

_SELECT_CONSENT = _COLUMNS + "WHERE id = %(id)s AND event_type = 'consent_granted'"

_SELECT_CONSENT_EVENTS = (
    _COLUMNS
    + "WHERE entity_patient = %(patient_key)s "
    + "AND event_type IN ('consent_granted', 'consent_revoked') ORDER BY seq"
)

_INSERT_AGGREGATE = """
INSERT INTO audit.aggregate_query_log (
    session_id, user_id, dataset, group_by, filters, cells, suppressed_cells, k_min, audit_id
) VALUES (
    %(session_id)s, %(user_id)s, %(dataset)s, %(group_by)s, %(filters)s, %(cells)s,
    %(suppressed_cells)s, %(k_min)s, %(audit_id)s
)
"""

_SELECT_SESSION_AGGREGATES = """
SELECT id, recorded_at, session_id, user_id, dataset, group_by, filters, cells,
       suppressed_cells, k_min, audit_id
FROM audit.aggregate_query_log
WHERE session_id = %(session_id)s
ORDER BY recorded_at
"""

_SELECT_ACTIVE_BREAK_GLASS = (
    _COLUMNS
    + """
WHERE event_type = 'break_glass'
  AND agent_user = %(user_id)s
  AND entity_patient = %(patient_key)s
  AND outcome = '0'
  AND (detail->>'expiry')::timestamptz > %(now)s
ORDER BY seq DESC
LIMIT 1
"""
)


class PgAuditWriter:
    """Writes to audit.audit_events as p360_app (INSERT + SELECT)."""

    def __init__(self, db: Database, *, agent_software: str, policy_version: str) -> None:
        self.db = db
        self.agent_software = agent_software
        self.policy_version = policy_version

    async def write(self, event: AuditEvent) -> UUID:
        if event.event_type not in EVENT_TYPES:
            raise ValueError(f"unknown audit event_type {event.event_type!r}")
        params = {
            "event_type": event.event_type,
            "agent_user": event.agent_user,
            "agent_software": event.agent_software or self.agent_software,
            "purpose_of_event": event.purpose_of_event,
            "entity_patient": event.entity_patient,
            "entity_resource": event.entity_resource,
            "entity_query": event.entity_query,
            "outcome": event.outcome,
            "outcome_desc": event.outcome_desc,
            "policy_id": event.policy_id,
            "policy_version": event.policy_version or self.policy_version,
            "reason_code": event.reason_code,
            "session_id": event.session_id,
            "jti": event.jti,
            "detail": Jsonb(event.detail),
        }
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(_INSERT, params)
                row = await cur.fetchone()
        except Exception as exc:  # any failure fails closed
            log.error("audit insert failed: %s", exc.__class__.__name__)
            raise Transient("audit unavailable") from exc
        if row is None:
            raise Transient("audit insert returned no id")
        return row["id"]

    async def _one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, params)
                return await cur.fetchone()
        except Exception as exc:
            log.error("audit read failed: %s", exc.__class__.__name__)
            raise Transient("audit unavailable") from exc

    async def _many(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(sql, params)
                return [dict(r) for r in await cur.fetchall()]
        except Exception as exc:
            log.error("audit read failed: %s", exc.__class__.__name__)
            raise Transient("audit unavailable") from exc

    async def get(self, audit_id: UUID) -> dict[str, Any] | None:
        return await self._one(_SELECT, {"id": audit_id})

    async def get_consent(self, consent_id: UUID) -> dict[str, Any] | None:
        return await self._one(_SELECT_CONSENT, {"id": consent_id})

    async def consent_events(self, patient_key: str) -> list[dict[str, Any]]:
        return await self._many(_SELECT_CONSENT_EVENTS, {"patient_key": patient_key})

    async def active_break_glass(
        self, user_id: str, patient_key: str, now: datetime
    ) -> dict[str, Any] | None:
        return await self._one(
            _SELECT_ACTIVE_BREAK_GLASS, {"user_id": user_id, "patient_key": patient_key, "now": now}
        )

    async def log_aggregate(
        self,
        *,
        session_id: str | None,
        user_id: str,
        dataset: str,
        group_by: list[str],
        filters: dict[str, Any],
        cells: list[dict[str, Any]],
        suppressed_cells: int,
        k_min: int | None,
        audit_id: UUID | None,
    ) -> None:
        params = {
            "session_id": session_id,
            "user_id": user_id,
            "dataset": dataset,
            "group_by": group_by,
            "filters": Jsonb(filters),
            "cells": Jsonb(cells),
            "suppressed_cells": suppressed_cells,
            "k_min": k_min,
            "audit_id": audit_id,
        }
        try:
            async with self.db.pool.connection() as conn:
                await conn.execute(_INSERT_AGGREGATE, params)
        except Exception as exc:
            log.error("aggregate log insert failed: %s", exc.__class__.__name__)
            raise Transient("audit unavailable") from exc

    async def session_aggregates(self, session_id: str) -> list[dict[str, Any]]:
        return await self._many(_SELECT_SESSION_AGGREGATES, {"session_id": session_id})

    async def list_events(self, *, limit: int = 100, agent_user: str | None = None) -> list[dict[str, Any]]:
        sql = _COLUMNS + (
            "WHERE agent_user = %(agent_user)s ORDER BY seq DESC LIMIT %(limit)s"
            if agent_user
            else "ORDER BY seq DESC LIMIT %(limit)s"
        )
        params: dict[str, Any] = {"limit": limit}
        if agent_user:
            params["agent_user"] = agent_user
        return await self._many(sql, params)
