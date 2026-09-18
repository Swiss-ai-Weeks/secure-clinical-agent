"""Dataset specs never expose key or pointer columns, and every query is pinned to the decision's patient."""

from __future__ import annotations

from datetime import date

import pytest

from patient360.pdp.models import Obligations
from patient360.pdp.relations import DATASETS as PDP_DATASETS
from patient360.tools.datasets import DATASETS, FORBIDDEN_OUTPUT_COLUMNS, build_query
from patient360.tools.schemas import QueryFilters


def test_pdp_and_tool_agree_on_dataset_names():
    assert set(PDP_DATASETS) == set(DATASETS)


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_no_key_or_pointer_columns_leak(name):
    spec = DATASETS[name]
    leaked = set(spec.output_columns) & FORBIDDEN_OUTPUT_COLUMNS
    assert not leaked, f"{name} exposes {leaked}"
    assert "cite_id" in spec.output_columns
    assert "confidentiality" in spec.output_columns and "sensitivity" in spec.output_columns


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_query_is_pinned_to_patient_and_parameterised(name):
    sql, params = build_query(DATASETS[name], "p_101", QueryFilters(), Obligations())
    assert "t.patient_key = %(patient_key)s" in sql
    assert params["patient_key"] == "p_101"
    assert "LIMIT %(limit)s" in sql and params["limit"] == 200
    assert "p_101" not in sql  # value travels as a parameter, never interpolated


def test_filters_only_narrow():
    f = QueryFilters(
        since=date(2026, 1, 1),
        until=date(2026, 9, 1),
        code="4548-4",
        category="laboratory",
        active_only=True,
        limit=5,
    )
    sql, params = build_query(DATASETS["labs"], "p_101", f, Obligations())
    assert sql.count(" AND ") >= 5
    assert params["since"] == date(2026, 1, 1) and params["until"] == date(2026, 9, 1)
    assert params["code"] == "4548-4" and params["category"] == "laboratory" and params["limit"] == 5
    assert "t.status IN ('final', 'amended', 'corrected')" in sql


def test_food_only_obligation_becomes_array_containment():
    sql, params = build_query(
        DATASETS["allergies"], "p_101", QueryFilters(), Obligations(allergy_category="food")
    )
    assert "t.category @> ARRAY[%(allergy_category)s]::text[]" in sql
    assert params["allergy_category"] == "food"
    sql2, params2 = build_query(
        DATASETS["labs"], "p_101", QueryFilters(), Obligations(allergy_category="food")
    )
    assert "allergy_category" not in sql2 and "allergy_category" not in params2


def test_unknown_filter_keys_are_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        QueryFilters(patient_key="p_999")  # type: ignore[call-arg]
