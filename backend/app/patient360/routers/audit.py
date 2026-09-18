"""GET /audit/{id}: one audit row, for the auditor role or for the row's own agent_user."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from ..auth.subject import DepsDep, SessionCallerDep
from ..errors import NotFound

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit_events(caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    agent = None if caller.user.role == "auditor" else caller.user.user_id
    events = await deps.audit_reader.list_events(limit=100, agent_user=agent)
    return {"events": events}


@router.get("/{audit_id}")
async def get_audit_event(audit_id: UUID, caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    row = await deps.audit_reader.get(audit_id)
    if row is None:
        raise NotFound()
    if caller.user.role != "auditor" and row.get("agent_user") != caller.user.user_id:
        raise NotFound()
    return row
