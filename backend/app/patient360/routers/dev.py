"""Dev surface (PATIENT360_DEV=true only).

POST /dev/run-token mints a run token for the current session so the agent
channel and the LLM06 token cases can be exercised before /chat exists. In
production /chat mints the token and hands it to the OpenShell credential
store; nothing returns it to a browser.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..auth import runtoken
from ..auth.subject import DepsDep, SessionCallerDep
from ..errors import NotFound

router = APIRouter(prefix="/dev", tags=["dev"])


class RunTokenRequest(BaseModel):
    agent_id: str = Field("agent:dev", pattern=r"^agent:[A-Za-z0-9_-]{1,64}$")


class RunTokenOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    jti: str
    sub: str
    act: dict[str, str]
    aud: str


@router.post("/run-token", response_model=RunTokenOut)
async def mint_run_token(body: RunTokenRequest, caller: SessionCallerDep, deps: DepsDep) -> RunTokenOut:
    if not deps.settings.dev:
        raise NotFound()
    token, claims = runtoken.mint(
        deps.settings, user_id=caller.user.user_id, sid=caller.session.sid, agent_id=body.agent_id
    )
    return RunTokenOut(
        access_token=token,
        expires_in=deps.settings.run_token_ttl_seconds,
        jti=claims.jti,
        sub=claims.sub,
        act={"sub": claims.act_sub},
        aud=deps.settings.run_token_audience,
    )
