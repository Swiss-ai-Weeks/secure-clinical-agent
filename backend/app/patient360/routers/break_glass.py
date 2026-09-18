"""POST /break-glass: a human, on the dashboard, with a typed justification (Build Plan §2, §4.2).

Writes a time-boxed `emergency` tuple, a `break_glass` audit row with purpose BTG and a
compliance flag, then performs break_glass_identity (the audited re-identification read)
and returns the banner. No tool exists for this; the agent cannot reach it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..humanwrites import break_glass

router = APIRouter(tags=["break-glass"])


class BreakGlassIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_key: str = Field(pattern=r"^p_[0-9a-z]+$", max_length=64)
    justification: str = Field(min_length=20, max_length=1000)


class BreakGlassOut(BaseModel):
    patient_key: str
    start: datetime
    expiry: datetime
    compliance_flag: bool
    audit_id: str
    decision_audit_id: str
    identity: dict[str, Any] | None
    identity_audit_id: str | None


@router.post("/break-glass", response_model=BreakGlassOut, status_code=status.HTTP_201_CREATED)
async def open_break_glass(body: BreakGlassIn, caller: SessionCallerDep, deps: DepsDep) -> BreakGlassOut:
    result = await break_glass(deps, caller, body.patient_key, body.justification, now=utcnow())
    return BreakGlassOut(
        patient_key=result.patient_key,
        start=result.start,
        expiry=result.expiry,
        compliance_flag=result.compliance_flag,
        audit_id=str(result.audit_id),
        decision_audit_id=str(result.decision_audit_id),
        identity=result.identity,
        identity_audit_id=str(result.identity_audit_id) if result.identity_audit_id else None,
    )
