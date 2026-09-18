"""Policy tables as data: the §4.2 check contract and the §3 dataset allowlist.

Which OpenFGA relation a read must hold, and which datasets a role may ask for
at all. Roles, duty, AAL, labels, and dataset allowlists are PDP rules; OpenFGA
holds relationships only.
"""

from __future__ import annotations

# Datasets served by /tools/query in this slice. notes and imaging have their own tools.
DATASETS = ("labs", "conditions", "meds", "encounters", "allergies", "diet")

# FHIR Resource Plan §3: per-patient datasets each role may read. A dataset outside
# the allowlist is the uniform not-found; the tool never touches the table.
ROLE_DATASETS: dict[str, frozenset[str]] = {
    "attending": frozenset({"labs", "conditions", "meds", "encounters", "allergies", "diet"}),
    "care_team": frozenset({"labs", "conditions", "meds", "encounters", "allergies", "diet"}),
    "consultant": frozenset({"labs", "conditions", "meds", "encounters", "allergies"}),
    "caregiver": frozenset({"labs", "conditions", "meds", "encounters", "allergies", "diet"}),
    "patient": frozenset({"labs", "conditions", "meds", "encounters", "allergies", "diet"}),
    "researcher": frozenset(),
    "dietary_staff": frozenset({"allergies", "diet"}),
    "auditor": frozenset(),
}

# Dashboard panels per role, derived from the same tables. /me returns them so the
# frontend gates panels on the server's view of the role, not its own.
ROLE_PANELS: dict[str, tuple[str, ...]] = {
    "attending": (
        "labs",
        "conditions",
        "meds",
        "encounters",
        "allergies",
        "diet",
        "notes",
        "imaging",
        "aggregate_own_patients",
        "consents",
        "break_glass",
        "appointments",
        "ask",
    ),
    "care_team": (
        "labs",
        "conditions",
        "meds",
        "encounters",
        "allergies",
        "diet",
        "notes",
        "imaging_metadata",
        "break_glass",
        "appointments",
        "ask",
    ),
    "consultant": (
        "labs",
        "conditions",
        "meds",
        "encounters",
        "allergies",
        "notes",
        "imaging",
        "break_glass",
        "ask",
    ),
    "caregiver": (
        "labs",
        "conditions",
        "meds",
        "encounters",
        "allergies",
        "diet",
        "notes",
        "appointments",
        "ask",
    ),
    "patient": (
        "portal",
        "labs",
        "conditions",
        "meds",
        "encounters",
        "allergies",
        "diet",
        "notes",
        "imaging_metadata",
        "consents",
        "appointments",
        "ask",
    ),
    "researcher": ("aggregate", "ask"),
    "dietary_staff": ("diet", "allergies_food", "aggregate_ward", "ask"),
    "auditor": ("audit",),
}


# Build Plan §4.2 grant authority, as data. A patient on the own record (PDP self match) may
# write and revoke these relations; a subject holding can_delegate (an attending) may write
# these and revoke only what they granted; a subject holding can_consent (a guardian) exercises
# the patient's own set on the minor's record. Compliance/admin roles are not in the demo.
GRANTABLE_BY_SELF = frozenset({"caregiver", "caregiver_notes", "blocked"})
GRANTABLE_BY_DELEGATE = frozenset({"care_team", "consultant"})
CONSENT_RELATIONS = GRANTABLE_BY_SELF | GRANTABLE_BY_DELEGATE

# Which permission a non-self subject must hold to write consents, by role, and what it grants.
AUTHORITY_BY_ROLE: dict[str, str] = {"attending": "can_delegate", "caregiver": "can_consent"}
GRANTABLE_BY_AUTHORITY: dict[str, frozenset[str]] = {
    "can_delegate": GRANTABLE_BY_DELEGATE,
    "can_consent": GRANTABLE_BY_SELF,
}
# Decision reason codes per authority; consent rows record it as detail.basis.
BASIS_BY_AUTHORITY: dict[str, str] = {"can_delegate": "relationship", "can_consent": "guardian"}

# What the consent listing shows: grantable relations plus the worker-written attending
# assignment, guardianship, and live break-glass activations. Ward placements are not consents.
LISTED_RELATIONS = CONSENT_RELATIONS | frozenset({"attending", "guardian", "emergency"})

# The identity.users role a grantee must hold for a relation. `blocked` may name any active user.
GRANTEE_ROLE_FOR_RELATION: dict[str, frozenset[str]] = {
    "caregiver": frozenset({"caregiver"}),
    "caregiver_notes": frozenset({"caregiver"}),
    "care_team": frozenset({"care_team"}),
    "consultant": frozenset({"consultant"}),
    "blocked": frozenset(ROLE_DATASETS),
}

# Care roles that may open break-glass (on duty, AAL2, dashboard channel). Dietary staff cannot.
BREAK_GLASS_ROLES = frozenset({"attending", "care_team", "consultant"})

# Roles that may see the identity banner on a patient they hold a relationship for.
IDENTITY_BANNER_ROLES = frozenset({"attending", "care_team", "consultant", "caregiver"})

# Datasets each role may aggregate (FHIR Resource Plan §3). Researcher has no
# per-patient datasets; attending own-cohort and dietary ward counts are scoped
# by list_objects, not by a patient_key in the body.
AGGREGATE_DATASETS: dict[str, frozenset[str]] = {
    "researcher": frozenset({"labs", "conditions", "meds", "encounters", "allergies"}),
    "attending": frozenset(DATASETS),
    "dietary_staff": frozenset({"diet", "allergies"}),
}

# column_policy.aggregate_dim plus the joined patient quasi-identifiers.
# Timestamp columns are deliberately absent (date_shift = reject, not shift).
AGGREGATE_DIMS: dict[str, frozenset[str]] = {
    "labs": frozenset({"code", "category", "interpretation", "sex", "birth_year"}),
    "conditions": frozenset({"code", "clinical_status", "category", "sex", "birth_year"}),
    "meds": frozenset({"code", "status", "sex", "birth_year"}),
    "encounters": frozenset({"status", "class", "type_code", "dept", "sex", "birth_year"}),
    "allergies": frozenset({"code", "category", "sex", "birth_year"}),
    "diet": frozenset({"diet_codes", "ward", "sex", "birth_year"}),
}


# Roles that may request notes / imaging at all. Others are the uniform not-found
# before OpenFGA (researcher and dietary staff never reach those tools).
NOTES_ROLES = frozenset({"attending", "care_team", "consultant", "caregiver", "patient"})
IMAGING_ROLES = frozenset({"attending", "care_team", "consultant", "caregiver", "patient"})
PIXEL_ROLES = frozenset({"attending", "consultant", "patient"})


def relation_for(resource_type: str, dataset: str | None, role: str) -> str | None:
    """Relation checked on patient:{patient_key} for this read (Build Plan §4.2 table)."""
    if resource_type == "clinical_rows":
        if dataset == "diet":
            return "can_read_diet"
        if dataset == "allergies" and role == "dietary_staff":
            return "can_read_diet"
        return "can_read_clinical"
    if resource_type == "notes":
        return "can_read_notes"
    if resource_type == "imaging_report":
        if role in ("care_team", "caregiver"):
            return "can_read_imaging_metadata"
        return "can_read_imaging_report"
    if resource_type in ("imaging_pixels", "document_bytes"):
        return "can_view_pixels"
    if resource_type == "identity":
        return "can_read_clinical"
    if resource_type == "consents":
        return "can_delegate"
    if resource_type == "aggregate":
        if role == "researcher":
            return "can_query_aggregate"
        if role == "dietary_staff":
            return "can_read_diet"
        if role == "attending":
            return "can_read_clinical"
        return None
    return None
