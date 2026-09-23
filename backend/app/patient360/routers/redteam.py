"""In-process red-team scoreboard. Cases live in backend/redteam/cases."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..auth.subject import DepsDep, SessionCallerDep
from ..redteam_run import load_cases, run_suite, summarize

router = APIRouter(tags=["redteam"])


def _catalog() -> dict[str, Any]:
    cases = [
        {**c, "layer": c.get("layer") or "pdp", "result": "catalogued", "mpib": c.get("owasp")}
        for c in load_cases()
    ]
    body = summarize(cases)
    body["asr"] = 0.0
    return body


@router.get("/redteam")
async def redteam_scoreboard(request: Request, caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    del deps
    cached = getattr(request.app.state, "redteam", None) or _catalog()
    cached = dict(cached)
    cached["viewer"] = caller.user.role
    return cached


@router.post("/redteam/run")
async def redteam_run(request: Request, caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    del deps
    cached = await run_suite(request.app)
    request.app.state.redteam = cached
    cached = dict(cached)
    cached["viewer"] = caller.user.role
    return cached
