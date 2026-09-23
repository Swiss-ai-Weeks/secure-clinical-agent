"""POST /patients/{patient_key}/studies/{study_id}/reprocess: dashboard CT overlay."""

from __future__ import annotations

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from ..auth.sessions import utcnow
from ..auth.subject import DepsDep, SessionCallerDep
from ..reprocess import ReprocessRequest, reprocess_ct

router = APIRouter(prefix="/patients", tags=["imaging"])


class ReprocessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classes: list[str] | None = Field(default=None, max_length=8)


class ReprocessOut(BaseModel):
    patient_key: str
    study_id: str
    classes: list[str]
    report_text: str
    series_uid: str
    report_source_id: str | None = None
    audit_id: str
    decision_audit_id: str


@router.post("/{patient_key}/studies/{study_id}/reprocess", response_model=ReprocessOut)
async def post_reprocess(
    caller: SessionCallerDep,
    deps: DepsDep,
    body: ReprocessIn,
    patient_key: str = Path(pattern=r"^p_[0-9a-z]+$", max_length=64),
    study_id: str = Path(min_length=1, max_length=64),
) -> dict:
    requested = body.classes
    return await reprocess_ct(
        deps,
        caller,
        ReprocessRequest(
            patient_key=patient_key,
            study_id=study_id,
            classes=tuple(requested) if requested else None,
        ),
        now=utcnow(),
    )
