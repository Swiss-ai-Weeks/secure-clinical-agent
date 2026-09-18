"""POST /appointments and PATCH /appointments/{id}: human book / cancel."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from ..appointments import BookRequest, book_appointment, cancel_appointment
from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep

router = APIRouter(tags=["appointments"])


class BookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_key: str = Field(pattern=r"^p_[0-9a-z]+$", max_length=64)
    practitioner_user_id: str = Field(pattern=r"^u_[0-9a-z]+$", max_length=64)
    start: datetime
    end: datetime | None = None
    dept: str | None = Field(None, max_length=64)
    service_type: str | None = Field(None, max_length=64)
    service_type_system: str | None = Field(None, max_length=128)
    service_type_display: str | None = Field(None, max_length=256)


class AppointmentOut(BaseModel):
    id: str
    cite_id: str | None = None
    patient_key: str
    practitioner_user_id: str
    status: str
    start: datetime | None = None
    end: datetime | None = None
    dept: str | None = None
    service_type_display: str | None = None
    created_by: str | None = None
    audit_id: str
    decision_audit_id: str


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern=r"^cancelled$")


@router.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def post_appointment(body: BookIn, caller: SessionCallerDep, deps: DepsDep) -> dict:
    return await book_appointment(
        deps,
        caller,
        BookRequest(
            patient_key=body.patient_key,
            practitioner_user_id=body.practitioner_user_id,
            start=body.start,
            end=body.end,
            dept=body.dept,
            service_type=body.service_type,
            service_type_system=body.service_type_system,
            service_type_display=body.service_type_display,
        ),
        now=utcnow(),
    )


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
async def patch_appointment(
    appointment_id: UUID, body: CancelIn, caller: SessionCallerDep, deps: DepsDep
) -> dict:
    del body  # status is locked to cancelled
    return await cancel_appointment(deps, caller, appointment_id, now=utcnow())
