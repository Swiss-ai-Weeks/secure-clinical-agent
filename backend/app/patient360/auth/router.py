"""/auth: dev-login, logout, and (dev only) the persona list for the switcher."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from ..errors import NotFound
from ..pdp.relations import ROLE_PANELS
from .subject import DepsDep, SessionCallerDep

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    # Demo toggles (Build Plan §9 steps 8 and step-up). In production these come from the IdP and the roster.
    on_duty: bool = True
    auth_level: int = Field(1, ge=1, le=2)


class SessionOut(BaseModel):
    expires_at: datetime
    absolute_expires_at: datetime
    auth_level: int
    on_duty: bool


class LoginOut(BaseModel):
    user_id: str
    display: str | None
    role: str
    department: str | None
    self_patient_id: str | None
    panels: list[str]
    session: SessionOut


class PersonaOut(BaseModel):
    login: str
    user_id: str
    display: str
    role: str | None = None
    panels: list[str] = Field(default_factory=list)


@router.post("/dev-login", response_model=LoginOut)
async def dev_login(body: DevLoginRequest, request: Request, response: Response, deps: DepsDep) -> LoginOut:
    prior = request.cookies.get(deps.settings.cookie_name)
    result = await deps.manager.login(
        body.login, on_duty=body.on_duty, auth_level=body.auth_level, prior_cookie=prior
    )
    response.set_cookie(
        key=deps.settings.cookie_name,
        value=result.token,
        max_age=deps.settings.session_absolute_seconds,
        path="/",
        secure=deps.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    s, u = result.session, result.user
    return LoginOut(
        user_id=u.user_id,
        display=deps.devlogin.display_for(u.user_id),
        role=u.role,
        department=u.department,
        self_patient_id=s.self_patient_id,
        panels=list(ROLE_PANELS.get(u.role, ())),
        session=SessionOut(
            expires_at=s.expires_at,
            absolute_expires_at=s.absolute_expires_at,
            auth_level=s.auth_level,
            on_duty=s.on_duty,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(caller: SessionCallerDep, response: Response, deps: DepsDep) -> Response:
    assert caller.cookie is not None
    await deps.manager.logout(caller.cookie)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=deps.settings.cookie_name, path="/")
    return response


@router.get("/dev-personas", response_model=list[PersonaOut])
async def dev_personas(deps: DepsDep) -> list[PersonaOut]:
    if not deps.settings.dev:
        raise NotFound()
    out: list[PersonaOut] = []
    for persona in deps.devlogin.personas():
        user = await deps.users.get(persona.user_id)
        role = user.role if user and user.active else None
        out.append(
            PersonaOut(
                login=persona.login,
                user_id=persona.user_id,
                display=persona.display,
                role=role,
                panels=list(ROLE_PANELS.get(role, ())) if role else [],
            )
        )
    return out
