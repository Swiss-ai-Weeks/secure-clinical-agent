"""Subject resolution: who is calling, over which channel.

Bearer at+JWT -> agent channel (the run token minted by the backend for this
session). Session cookie -> dashboard channel. Neither -> 401. Identity never
comes from a request body; tool arguments carrying identity are ignored and
logged by the tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request

from ..deps import AppDeps, get_deps
from ..errors import Unauthenticated
from ..pdp.models import Channel, Subject
from . import runtoken
from .sessions import Session, User, utcnow


@dataclass(frozen=True, slots=True)
class Caller:
    subject: Subject
    channel: Channel
    session: Session
    user: User
    cookie: str | None = None
    jti: str | None = None
    agent: str | None = None  # act.sub on the agent channel

    @property
    def sid(self) -> str:
        return self.session.sid


def subject_from(session: Session, user: User) -> Subject:
    return Subject(
        user_id=user.user_id,
        role=user.role,
        department=user.department,
        credential_level=user.credential_level,
        on_duty=session.on_duty,
        auth_level=session.auth_level,
        self_patient_id=session.self_patient_id,
    )


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if not auth:
        return None
    scheme, _, value = auth.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise Unauthenticated("malformed authorization header")
    return value.strip()


async def _from_cookie(request: Request, deps: AppDeps, now: datetime) -> Caller:
    cookie = request.cookies.get(deps.settings.cookie_name)
    if not cookie:
        raise Unauthenticated("no session")
    session, user = await deps.manager.authenticate(cookie, now=now)
    return Caller(
        subject=subject_from(session, user), channel="dashboard", session=session, user=user, cookie=cookie
    )


async def _from_token(token: str, deps: AppDeps, now: datetime) -> Caller:
    claims = runtoken.verify(deps.settings, token, now=now)
    session, user = await deps.manager.session_for_sid(claims.sid, now=now)
    if user.user_id != claims.user_id:
        raise Unauthenticated("token subject does not match session")
    return Caller(
        subject=subject_from(session, user),
        channel="agent",
        session=session,
        user=user,
        jti=claims.jti,
        agent=claims.act_sub,
    )


async def current_caller(request: Request, deps: Annotated[AppDeps, Depends(get_deps)]) -> Caller:
    """Tool endpoints: run token first (agent channel), else session cookie (dashboard)."""
    now = utcnow()
    token = _bearer(request)
    if token is not None:
        return await _from_token(token, deps, now)
    return await _from_cookie(request, deps, now)


async def session_caller(request: Request, deps: Annotated[AppDeps, Depends(get_deps)]) -> Caller:
    """Dashboard-only endpoints: the cookie is the only accepted credential. A run token is refused."""
    if _bearer(request) is not None:
        raise Unauthenticated("run tokens are not accepted here")
    return await _from_cookie(request, deps, utcnow())


CallerDep = Annotated[Caller, Depends(current_caller)]
SessionCallerDep = Annotated[Caller, Depends(session_caller)]
DepsDep = Annotated[AppDeps, Depends(get_deps)]
