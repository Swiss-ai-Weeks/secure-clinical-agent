"""POST /tools/query request and response shapes."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Dataset = Literal["labs", "conditions", "meds", "encounters", "allergies", "diet"]

# Argument names that would carry identity if a caller (or a prompt) tried. They are
# never read; the tool logs them on the audit row as ignored.
IDENTITY_ARG_NAMES = frozenset(
    {"user_id", "user", "role", "subject", "on_behalf_of", "act", "session_id", "token"}
)


class QueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: date | None = None
    until: date | None = None
    code: str | None = Field(None, max_length=64)
    category: str | None = Field(None, max_length=64)
    active_only: bool = False
    limit: int = Field(200, ge=1, le=1000)


class AggregateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_by: list[str] = Field(default_factory=list, max_length=4)
    measure: Literal["count"] = "count"
    project_id: str | None = None


class QueryRequest(BaseModel):
    # extra="allow" so identity smuggled into the body is captured for the audit row, then ignored.
    model_config = ConfigDict(extra="allow")

    patient_key: str | None = Field(None, pattern=r"^p_[0-9a-z]+$", max_length=64)
    dataset: Dataset
    filters: QueryFilters = Field(default_factory=QueryFilters)
    aggregate: AggregateSpec | None = None

    def ignored_args(self) -> list[str]:
        return sorted(self.model_extra or {})

    def ignored_identity_args(self) -> list[str]:
        return sorted(k for k in (self.model_extra or {}) if k.lower() in IDENTITY_ARG_NAMES)


class DecisionOut(BaseModel):
    effect: Literal["permit", "deny", "not_found"]
    reason_code: str
    policy_id: str
    policy_version: str
    relation: str | None = None
    purpose_of_event: str = "TREAT"
    # True when the read rides on a live break-glass activation by this user on this patient (purpose BTG).
    compliance_flag: bool = False


class NotesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    patient_key: str = Field(..., pattern=r"^p_[0-9a-z]+$", max_length=64)
    question: str = Field("", max_length=2000)

    def ignored_args(self) -> list[str]:
        return sorted(self.model_extra or {})


class NotesResponse(BaseModel):
    patient_key: str
    chunks: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    chunk_count: int
    obligations: dict[str, Any]
    decision: DecisionOut
    audit_id: UUID


class ImagingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    patient_key: str = Field(..., pattern=r"^p_[0-9a-z]+$", max_length=64)
    study_id: str | None = Field(None, max_length=64)
    classes: list[str] | None = Field(default=None, max_length=8)

    def ignored_args(self) -> list[str]:
        return sorted(self.model_extra or {})


class ImagingResponse(BaseModel):
    patient_key: str
    studies: list[dict[str, Any]]
    reports: list[dict[str, Any]]
    obligations: dict[str, Any]
    decision: DecisionOut
    audit_id: UUID
    overlay_classes: list[str] | None = None
    overlay_text: str | None = None
    overlay_study_id: str | None = None
    allowed_classes: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    patient_key: str | None = None
    dataset: Dataset
    rows: list[dict[str, Any]]
    row_count: int
    redacted_count: int = 0
    suppressed_cells: int = 0
    obligations: dict[str, Any]
    decision: DecisionOut
    audit_id: UUID
