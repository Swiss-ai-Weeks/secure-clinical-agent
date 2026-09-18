"""k-min suppression, complementary siblings, and conservative overlap (Build Plan §2)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .schemas import QueryFilters


def age_display(birth_year: int | None, at_year: int) -> str | None:
    """Mirror clinical.age_display(): year precision, ages >= 90 reported as 90+."""
    if birth_year is None:
        return None
    age = at_year - birth_year
    return "90+" if age >= 90 else str(age)


def filter_equalities(filters: QueryFilters) -> dict[str, str]:
    """The equalities the overlap rule compares: code, category, date bounds."""
    out: dict[str, str] = {}
    if filters.code:
        out["code"] = filters.code
    if filters.category:
        out["category"] = filters.category
    if filters.since is not None:
        out["since"] = filters.since.isoformat() if isinstance(filters.since, date) else str(filters.since)
    if filters.until is not None:
        out["until"] = filters.until.isoformat() if isinstance(filters.until, date) else str(filters.until)
    return out


def differs_by_one_equality(left: dict[str, str], right: dict[str, str]) -> bool:
    keys = set(left) | set(right)
    return sum(1 for k in keys if left.get(k) != right.get(k)) == 1


def overlaps_prior(
    dataset: str,
    group_by: list[str],
    filters: QueryFilters,
    prior: list[dict[str, Any]],
) -> bool:
    """True when a prior answered query on the same dataset/group_by differs by one equality."""
    incoming = filter_equalities(filters)
    incoming_dims = list(group_by)
    for row in prior:
        if row.get("dataset") != dataset:
            continue
        if list(row.get("group_by") or []) != incoming_dims:
            continue
        prior_filters = row.get("filters") or {}
        if not isinstance(prior_filters, dict):
            continue
        prior_eq = {k: str(v) for k, v in prior_filters.items() if v is not None}
        if differs_by_one_equality(incoming, prior_eq):
            return True
    return False


def apply_suppression(
    raw: list[dict[str, Any]], group_by: list[str], k_min: int | None
) -> list[dict[str, Any]]:
    """Blank cells below k_min; suppress the last sibling that would recover them."""
    cells: list[dict[str, Any]] = []
    for row in raw:
        dims = {k: row.get(k) for k in group_by}
        cells.append({"dims": dims, "count": int(row["count"]), "suppressed": False})
    if not k_min:
        return cells
    for cell in cells:
        if (cell["count"] or 0) < k_min:
            cell["suppressed"] = True
            cell["count"] = None
    parent_dims = group_by[:-1]
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        key = tuple(cell["dims"].get(d) for d in parent_dims)
        buckets[key].append(cell)
    for siblings in buckets.values():
        changed = True
        while changed:
            changed = False
            unsuppressed = [s for s in siblings if not s["suppressed"]]
            suppressed = [s for s in siblings if s["suppressed"]]
            if unsuppressed and suppressed and len(unsuppressed) == 1:
                unsuppressed[0]["suppressed"] = True
                unsuppressed[0]["count"] = None
                changed = True
    return cells
