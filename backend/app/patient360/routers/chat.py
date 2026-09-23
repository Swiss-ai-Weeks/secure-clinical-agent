from __future__ import annotations

from fastapi import APIRouter

from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..chat import ChatRequest, run_chat
from ..openshell import session_sandbox_status

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(body: ChatRequest, caller: SessionCallerDep, deps: DepsDep) -> dict:
    return await run_chat(deps, caller, body, now=utcnow())


@router.get("/chat/sandbox")
async def chat_sandbox(caller: SessionCallerDep, deps: DepsDep) -> dict:
    """Live session sandbox only. No sandbox name. Inactive means old chats stay closed."""
    return await session_sandbox_status(deps.settings, caller.session.sandbox_id)
