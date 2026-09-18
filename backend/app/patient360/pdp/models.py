"""PDP input and output types (Build Plan §4.1).

Subject is resolved server-side from the session or the run token, never from a
prompt or a tool argument. Resource carries what is being read; Context carries
when, over which channel, and for what purpose. Decision is the effect plus the
obligations the store-side enforcement must apply.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

ResourceType = Literal[
    "clinical_rows",
    "notes",
    "imaging_report",
    "imaging_pixels",
    "document_bytes",
    "aggregate",
    "identity",
    "consents",
]
Channel = Literal["agent", "dashboard"]
Action = Literal["read", "schedule", "cancel", "consent_grant", "consent_revoke", "break_glass"]
Effect = Literal["permit", "deny", "not_found"]

# HL7 v3 Confidentiality codes used on every clinical row.
CONFIDENTIALITY = ("N", "R", "V")

# identity.vs_user_role()
ROLES = (
    "attending",
    "care_team",
    "consultant",
    "caregiver",
    "patient",
    "researcher",
    "dietary_staff",
    "auditor",
)
CARE_ROLES = frozenset({"attending", "care_team", "consultant", "dietary_staff"})

# audit.vs_purpose_of_use() by role: v3-PurposeOfUse
PURPOSE_BY_ROLE = {
    "attending": "TREAT",
    "care_team": "TREAT",
    "consultant": "TREAT",
    "caregiver": "PATRQT",
    "patient": "PATRQT",
    "researcher": "HRESCH",
    "dietary_staff": "HOPERAT",
    "auditor": "HOPERAT",
}


@dataclass(frozen=True, slots=True)
class Subject:
    user_id: str
    role: str
    department: str | None
    credential_level: int
    on_duty: bool
    auth_level: int
    self_patient_id: str | None


@dataclass(frozen=True, slots=True)
class Resource:
    type: ResourceType
    patient_key: str | None = None
    dataset: str | None = None
    confidentiality: str = "N"
    sensitivity: tuple[str, ...] = ()
    # Approximate age from clinical.patients.birth_year (year precision, like age_display()).
    # Drives the adolescent-confidentiality rule for caregiver-role readers. None when unknown.
    patient_age: int | None = None


@dataclass(frozen=True, slots=True)
class WriteTarget:
    """A consent write's relation and grantee. The grantee role comes from identity.users, not the body."""

    relation: str
    grantee_user_id: str | None = None
    grantee_role: str | None = None  # None when the grantee is not an active identity.users row
    granted_by: str | None = None  # on revoke: agent_user of the consent_granted row


@dataclass(frozen=True, slots=True)
class Context:
    now: datetime
    channel: Channel
    purpose: str
    action: Action = "read"
    jti: str | None = None
    group_by: tuple[str, ...] | None = None
    project_id: str | None = None
    k_min: int | None = None
    allowed_dims: tuple[str, ...] | None = None
    target: WriteTarget | None = None
    # Cancel: the appointment row's booker and practitioner (PDP rule on the row).
    appointment_created_by: str | None = None
    appointment_practitioner: str | None = None
    # Policy thresholds (settings). Between them, a caregiver-role reader (guardian or named
    # caregiver) sees R/V rows redacted: confidential adolescent care.
    adolescent_age: int = 14
    majority_age: int = 18


@dataclass(slots=True)
class Obligations:
    # confidentiality label -> reason ('REDACT' for a role rule, 'step_up_required' for an AAL rule)
    redact: dict[str, str] = field(default_factory=dict)
    # self view: clinician-internal notes are omitted
    exclude_internal: bool = False
    # dietary staff: only allergies with this category
    allergy_category: str | None = None
    # aggregate path
    k_min: int | None = None
    date_shift: bool = False
    allowed_dims: tuple[str, ...] | None = None
    # imaging_report: metadata (care_team / self / guardian) or report text
    imaging_tier: str | None = None

    @property
    def redact_labels(self) -> frozenset[str]:
        return frozenset(self.redact)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, False, {}, ())}


@dataclass(slots=True)
class Decision:
    effect: Effect
    reason_code: str
    policy_id: str
    obligations: Obligations = field(default_factory=Obligations)
    relation: str | None = None
    fga_consulted: bool = False
    audit_id: UUID | None = None
    # Set by the caller when the permit rides on a live break-glass activation (purpose BTG).
    compliance_flag: bool = False
    # Aggregate scope from list_objects (attending / dietary). None = researcher (all rows).
    scoped_keys: tuple[str, ...] | None = None

    @property
    def permitted(self) -> bool:
        return self.effect == "permit"
