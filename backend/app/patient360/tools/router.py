"""/tools/*: read-only, PDP on every call."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from ..appointments import availability
from ..auth.sessions import utcnow
from ..auth.subject import CallerDep, DepsDep
from .imaging import run_imaging
from .notes import run_notes
from .query import run_query
from .schemas import ImagingRequest, ImagingResponse, NotesRequest, NotesResponse, QueryRequest, QueryResponse

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/query", response_model=QueryResponse, responses={404: {"description": "Uniform not found"}})
async def tools_query(body: QueryRequest, caller: CallerDep, deps: DepsDep) -> QueryResponse:
    return await run_query(deps, caller, body, now=utcnow())


@router.post("/notes", response_model=NotesResponse, responses={404: {"description": "Uniform not found"}})
async def tools_notes(body: NotesRequest, caller: CallerDep, deps: DepsDep) -> NotesResponse:
    return await run_notes(deps, caller, body, now=utcnow())


@router.post(
    "/imaging", response_model=ImagingResponse, responses={404: {"description": "Uniform not found"}}
)
async def tools_imaging(body: ImagingRequest, caller: CallerDep, deps: DepsDep) -> ImagingResponse:
    return await run_imaging(deps, caller, body, now=utcnow())


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: str | None = Field(None, max_length=64)
    practitioner_user_id: str | None = Field(None, pattern=r"^u_[0-9a-z]+$", max_length=64)


@router.post("/availability")
async def tools_availability(body: AvailabilityIn, caller: CallerDep, deps: DepsDep) -> dict:
    del caller  # authenticated; slots are opaque ids
    slots = await availability(
        deps,
        now=utcnow(),
        department=body.department,
        practitioner_user_id=body.practitioner_user_id,
    )
    return {"slots": slots, "count": len(slots)}
