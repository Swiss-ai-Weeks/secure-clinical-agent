"""Dataset specs for /tools/query: table, allowlisted output columns, filters.

Every query is `WHERE t.patient_key = %(patient_key)s` with the key taken from
the PDP decision, never from a caller filter. Output columns are an allowlist:
surrogate ids, source ids, foreign keys, and pointer columns (column_policy
classes key and pointer) are never selected; cite_id is the citation handle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..clinical_view import CLINICAL_CONDITION_WHERE, LAB_CLINICAL_CATEGORY_WHERE
from ..pdp.models import Obligations
from .schemas import QueryFilters

# clinical.column_policy classes `key` and `pointer`, plus anything that would leak a join.
FORBIDDEN_OUTPUT_COLUMNS = frozenset(
    {
        "id",
        "source_id",
        "patient_key",
        "encounter_id",
        "parent_id",
        "reason_condition_id",
        "study_id",
        "report_id",
        "observation_id",
        "allergy_ids",
        "sanitized_ref",
        "orthanc_id",
        "report_ref",
    }
)

LABELS = {"confidentiality": "t.confidentiality", "sensitivity": "t.sensitivity"}


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    from_sql: str  # FROM clause; the main table is aliased t
    columns: dict[str, str]  # output name -> SQL expression
    order_by: str
    since_column: str | None = None
    code_column: str | None = None
    category_column: str | None = None
    category_is_array: bool = False
    active_sql: str | None = None
    fixed_where: tuple[str, ...] = field(default_factory=tuple)

    @property
    def output_columns(self) -> tuple[str, ...]:
        return tuple(self.columns)


DATASETS: dict[str, DatasetSpec] = {
    "labs": DatasetSpec(
        name="labs",
        from_sql="clinical.observations t LEFT JOIN clinical.observations p ON p.id = t.parent_id",
        columns={
            "cite_id": "t.cite_id",
            "status": "t.status",
            "category": "t.category",
            "code": "t.code",
            "code_system": "t.code_system",
            "display": "t.display",
            "effective_at": "t.effective_at",
            "issued_at": "t.issued_at",
            "value_num": "t.value_num",
            "unit": "t.unit",
            "value_code": "t.value_code",
            "value_display": "t.value_display",
            "value_text": "t.value_text",
            "value_bool": "t.value_bool",
            "interpretation": "t.interpretation",
            "ref_low": "t.ref_low",
            "ref_high": "t.ref_high",
            "ref_text": "t.ref_text",
            "component_of": "p.cite_id",
            **LABELS,
        },
        order_by="t.effective_at DESC NULLS LAST, t.cite_id",
        since_column="t.effective_at",
        code_column="t.code",
        category_column="t.category",
        active_sql="t.status IN ('final', 'amended', 'corrected')",
        fixed_where=(LAB_CLINICAL_CATEGORY_WHERE,),
    ),
    "conditions": DatasetSpec(
        name="conditions",
        from_sql="clinical.conditions t",
        columns={
            "cite_id": "t.cite_id",
            "code": "t.code",
            "code_system": "t.code_system",
            "display": "t.display",
            "clinical_status": "t.clinical_status",
            "verification_status": "t.verification_status",
            "category": "t.category",
            "onset_date": "t.onset_date",
            "abatement_date": "t.abatement_date",
            "recorded_date": "t.recorded_date",
            **LABELS,
        },
        order_by="t.onset_date DESC NULLS LAST, t.cite_id",
        since_column="t.onset_date",
        code_column="t.code",
        category_column="t.category",
        active_sql="t.clinical_status IN ('active', 'recurrence', 'relapse')",
        fixed_where=(CLINICAL_CONDITION_WHERE,),
    ),
    "meds": DatasetSpec(
        name="meds",
        from_sql="clinical.medications t LEFT JOIN clinical.conditions c ON c.id = t.reason_condition_id",
        columns={
            "cite_id": "t.cite_id",
            "status": "t.status",
            "intent": "t.intent",
            "code": "t.code",
            "code_system": "t.code_system",
            "display": "t.display",
            "authored_at": "t.authored_at",
            "dosage_text": "t.dosage_text",
            "timing_frequency": "t.timing_frequency",
            "timing_period": "t.timing_period",
            "timing_period_unit": "t.timing_period_unit",
            "dose_value": "t.dose_value",
            "dose_unit": "t.dose_unit",
            "as_needed": "t.as_needed",
            "reason_condition": "c.cite_id",
            **LABELS,
        },
        order_by="t.authored_at DESC NULLS LAST, t.cite_id",
        since_column="t.authored_at",
        code_column="t.code",
        active_sql="t.status = 'active'",
    ),
    "encounters": DatasetSpec(
        name="encounters",
        from_sql="clinical.encounters t",
        columns={
            "cite_id": "t.cite_id",
            "status": "t.status",
            "class": "t.class",
            "type_code": "t.type_code",
            "type_system": "t.type_system",
            "type_display": "t.type_display",
            "started_at": "t.started_at",
            "ended_at": "t.ended_at",
            "reason_code": "t.reason_code",
            "reason_system": "t.reason_system",
            "reason_display": "t.reason_display",
            "dept": "t.dept",
            **LABELS,
        },
        order_by="t.started_at DESC NULLS LAST, t.cite_id",
        since_column="t.started_at",
        code_column="t.type_code",
        category_column="t.class",
        active_sql="t.status IN ('planned', 'arrived', 'triaged', 'in-progress', 'onleave')",
    ),
    "allergies": DatasetSpec(
        name="allergies",
        from_sql="clinical.allergies t",
        columns={
            "cite_id": "t.cite_id",
            "clinical_status": "t.clinical_status",
            "verification_status": "t.verification_status",
            "type": "t.type",
            "category": "t.category",
            "criticality": "t.criticality",
            "code": "t.code",
            "code_system": "t.code_system",
            "display": "t.display",
            "reaction_code": "t.reaction_code",
            "reaction_system": "t.reaction_system",
            "reaction_display": "t.reaction_display",
            "severity": "t.severity",
            "recorded_date": "t.recorded_date",
            "onset_date": "t.onset_date",
            **LABELS,
        },
        order_by="t.recorded_date DESC NULLS LAST, t.cite_id",
        since_column="t.recorded_date",
        code_column="t.code",
        category_column="t.category",
        category_is_array=True,
        active_sql="t.clinical_status = 'active'",
    ),
    "diet": DatasetSpec(
        name="diet",
        from_sql="clinical.diet_orders t",
        columns={
            "cite_id": "t.cite_id",
            "status": "t.status",
            "intent": "t.intent",
            "ordered_at": "t.ordered_at",
            "diet_codes": "t.diet_codes",
            "texture": "t.texture",
            "fluid_consistency": "t.fluid_consistency",
            "exclude_food_modifiers": "t.exclude_food_modifiers",
            "ward": "t.ward",
            **LABELS,
        },
        order_by="t.ordered_at DESC NULLS LAST, t.cite_id",
        since_column="t.ordered_at",
        active_sql="t.status = 'active'",
    ),
}


def build_query(
    spec: DatasetSpec, patient_key: str, filters: QueryFilters, obligations: Obligations
) -> tuple[str, dict[str, Any]]:
    """Parameterised SQL. The patient key is the decision's, and every fragment only narrows."""
    where: list[str] = ["t.patient_key = %(patient_key)s", *spec.fixed_where]
    params: dict[str, Any] = {"patient_key": patient_key, "limit": filters.limit}
    _filter_where(spec, filters, obligations, where, params)

    select = ", ".join(f"{expr} AS {name}" for name, expr in spec.columns.items())
    sql = (
        f"SELECT {select} FROM {spec.from_sql} WHERE {' AND '.join(where)} "
        f"ORDER BY {spec.order_by} LIMIT %(limit)s"
    )
    return sql, params


# SQL expressions for aggregate dims. `pat` is clinical.patients when joined.
# `p` is already the parent observation on the labs spec, so patients cannot reuse it.
AGGREGATE_DIM_SQL: dict[str, str] = {
    "code": "t.code",
    "category": "t.category",
    "interpretation": "t.interpretation",
    "clinical_status": "t.clinical_status",
    "status": "t.status",
    "class": "t.class",
    "type_code": "t.type_code",
    "dept": "t.dept",
    "diet_codes": "t.diet_codes",
    "ward": "t.ward",
    "sex": "pat.sex",
    "birth_year": "clinical.age_display(pat.birth_year)",
}

PATIENT_DIMS = frozenset({"sex", "birth_year"})


def _code_label_sql(spec: DatasetSpec, group_by: list[str]) -> str | None:
    """Sidecar display for a coded dim. Not itself a group-by / allowed dim."""
    if "code" in group_by and "display" in spec.columns:
        return f"MIN({spec.columns['display']}) AS display"
    if "type_code" in group_by and "type_display" in spec.columns:
        return f"MIN({spec.columns['type_display']}) AS display"
    return None


def _filter_where(
    spec: DatasetSpec,
    filters: QueryFilters,
    obligations: Obligations,
    where: list[str],
    params: dict[str, Any],
) -> None:
    if filters.since is not None and spec.since_column:
        where.append(f"{spec.since_column} >= %(since)s")
        params["since"] = filters.since
    if filters.until is not None and spec.since_column:
        where.append(f"{spec.since_column} < %(until)s")
        params["until"] = filters.until
    if filters.code and spec.code_column:
        where.append(f"{spec.code_column} = %(code)s")
        params["code"] = filters.code
    if filters.category and spec.category_column:
        if spec.category_is_array:
            where.append(f"{spec.category_column} @> ARRAY[%(category)s]::text[]")
        else:
            where.append(f"{spec.category_column} = %(category)s")
        params["category"] = filters.category
    if filters.active_only and spec.active_sql:
        where.append(spec.active_sql)
    if obligations.allergy_category and spec.name == "allergies":
        where.append("t.category @> ARRAY[%(allergy_category)s]::text[]")
        params["allergy_category"] = obligations.allergy_category


def build_aggregate_query(
    spec: DatasetSpec,
    group_by: list[str],
    filters: QueryFilters,
    obligations: Obligations,
    scoped_keys: tuple[str, ...] | None,
) -> tuple[str, dict[str, Any]]:
    """COUNT(*) grouped by allowlisted dims. scoped_keys=None means every patient."""
    from_sql = spec.from_sql
    if PATIENT_DIMS & set(group_by) and "clinical.patients pat" not in from_sql:
        from_sql = f"{from_sql} JOIN clinical.patients pat ON pat.patient_key = t.patient_key"
    where: list[str] = list(spec.fixed_where)
    params: dict[str, Any] = {}
    if scoped_keys is not None:
        where.append("t.patient_key = ANY(%(scoped_keys)s)")
        params["scoped_keys"] = list(scoped_keys)
    _filter_where(spec, filters, obligations, where, params)
    where_sql = " AND ".join(where) if where else "TRUE"
    if group_by:
        select = ", ".join(f"{AGGREGATE_DIM_SQL[d]} AS {d}" for d in group_by)
        label = _code_label_sql(spec, group_by)
        if label:
            select = f"{select}, {label}"
        group_sql = ", ".join(AGGREGATE_DIM_SQL[d] for d in group_by)
        sql = (
            f"SELECT {select}, COUNT(*)::int AS count FROM {from_sql} WHERE {where_sql} GROUP BY {group_sql}"
        )
    else:
        sql = f"SELECT COUNT(*)::int AS count FROM {from_sql} WHERE {where_sql}"
    return sql, params
