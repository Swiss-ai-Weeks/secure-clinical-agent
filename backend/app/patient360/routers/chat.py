from __future__ import annotations

from fastapi import APIRouter

from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..chat import ChatRequest, run_chat

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(body: ChatRequest, caller: SessionCallerDep, deps: DepsDep) -> dict:
    return await run_chat(deps, caller, body, now=utcnow())
