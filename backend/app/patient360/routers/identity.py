"""GET /patients/{patient_key}/identity: the identity banner (name, DOB, sex, MRN) for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Path
from pydantic import BaseModel

from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..identity import identity_banner

router = APIRouter(prefix="/patients", tags=["identity"])


class BannerOut(BaseModel):
    patient_key: str
    given_name: str
    family_name: str
    birth_date: str
    sex: str
    mrn: str | None
    purpose_of_event: str
    compliance_flag: bool
    audit_id: str
    identity_audit_id: str


@router.get("/{patient_key}/identity", response_model=BannerOut)
async def get_identity_banner(
    caller: SessionCallerDep,
    deps: DepsDep,
    patient_key: str = Path(pattern=r"^p_[0-9a-z]+$", max_length=64),
) -> BannerOut:
    result = await identity_banner(deps, caller, patient_key, now=utcnow())
    return BannerOut(
        **result.banner,
        purpose_of_event=result.purpose_of_event,
        compliance_flag=result.compliance_flag,
        audit_id=str(result.audit_id),
        identity_audit_id=str(result.identity_audit_id),
    )
