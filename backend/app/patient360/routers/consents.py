"""/consents: grant, revoke, list. Dashboard channel only; tuple + audit row in one handler."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field

from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..humanwrites import ConsentGrantRequest, grant_consent, list_consents, revoke_consent

router = APIRouter(prefix="/consents", tags=["consents"])

Relation = Literal["caregiver", "caregiver_notes", "blocked", "care_team", "consultant"]


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_key: str = Field(pattern=r"^p_[0-9a-z]+$", max_length=64)
    grantee_user_id: str = Field(pattern=r"^u_[0-9a-z]+$", max_length=64)
    relation: Relation
    start: datetime | None = None
    expiry: datetime | None = None  # required unless relation is `blocked`
    justification: str | None = Field(None, max_length=500)


class ConsentOut(BaseModel):
    consent_id: str | None
    patient_key: str
    grantee_user_id: str
    relation: str
    start: datetime | None
    expiry: datetime | None
    status: str
    granted_by: str | None = None
    recorded_at: datetime | None = None
    justification: str | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    enforced: bool
    seeded: bool = False


class RevokeOut(BaseModel):
    consent_id: str
    patient_key: str
    grantee_user_id: str
    relation: str
    revoked_at: datetime
    tuple_removed: bool
    audit_id: str


class ConsentListOut(BaseModel):
    patient_key: str
    consents: list[ConsentOut]
    audit_id: str


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        from datetime import UTC

        return dt.replace(tzinfo=UTC)
    return dt


@router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
async def create_consent(body: GrantIn, caller: SessionCallerDep, deps: DepsDep) -> ConsentOut:
    req = ConsentGrantRequest(
        patient_key=body.patient_key,
        grantee_user_id=body.grantee_user_id,
        relation=body.relation,
        start=_aware(body.start),
        expiry=_aware(body.expiry),
        justification=body.justification,
    )
    record = await grant_consent(deps, caller, req, now=utcnow())
    return ConsentOut(**record.as_dict())


@router.post("/{consent_id}/revoke", response_model=RevokeOut)
async def revoke(consent_id: UUID, caller: SessionCallerDep, deps: DepsDep) -> RevokeOut:
    out: dict[str, Any] = await revoke_consent(deps, caller, consent_id, now=utcnow())
    return RevokeOut(**out)


@router.get("", response_model=ConsentListOut)
async def list_for_patient(
    caller: SessionCallerDep,
    deps: DepsDep,
    patient: str = Query(pattern=r"^p_[0-9a-z]+$", max_length=64),
) -> ConsentListOut:
    records, audit_id = await list_consents(deps, caller, patient, now=utcnow())
    return ConsentListOut(
        patient_key=patient, consents=[ConsentOut(**r.as_dict()) for r in records], audit_id=str(audit_id)
    )
