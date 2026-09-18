"""GET /me: the manifest the dashboard gates its panels on."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from ..auth.subject import DepsDep, SessionCallerDep
from ..pdp.relations import ROLE_DATASETS, ROLE_PANELS

router = APIRouter(tags=["me"])


class MeSession(BaseModel):
    expires_at: datetime
    absolute_expires_at: datetime
    auth_level: int
    on_duty: bool


class MeOut(BaseModel):
    user_id: str
    display: str | None
    role: str
    department: str | None
    credential_level: int
    self_patient_id: str | None
    datasets: list[str]
    panels: list[str]
    policy_version: str
    session: MeSession


@router.get("/me", response_model=MeOut)
async def me(caller: SessionCallerDep, deps: DepsDep) -> MeOut:
    s, u = caller.session, caller.user
    return MeOut(
        user_id=u.user_id,
        display=deps.devlogin.display_for(u.user_id),
        role=u.role,
        department=u.department,
        credential_level=u.credential_level,
        self_patient_id=s.self_patient_id,
        datasets=sorted(ROLE_DATASETS.get(u.role, frozenset())),
        panels=list(ROLE_PANELS.get(u.role, ())),
        policy_version=deps.policy_version,
        session=MeSession(
            expires_at=s.expires_at,
            absolute_expires_at=s.absolute_expires_at,
            auth_level=s.auth_level,
            on_duty=s.on_duty,
        ),
    )
