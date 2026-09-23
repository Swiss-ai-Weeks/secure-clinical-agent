"""Cross-store note publication.

A note is released only when Postgres, Qdrant, and this ledger agree. Raw Synthea
rows outside the three showcase keys are withheld (the leftover 97 stay unindexed).
Presidio failures are quarantined and never published. The authored demo cohort
(p_101, p_103) is not part of that leftover population.
"""

from __future__ import annotations

from typing import Any

# seed_grants.SHOWCASE_SYNTHEA_KEYS — Chen's three approved Synthea charts.
SHOWCASE_KEYS = frozenset(
    {
        "p_56fc60ea6ccd458496bba589b932e26d",
        "p_b1ef4e59dd984d828f102e37a3a5cd77",
        "p_485ba8c8597d4c5cb0fbda55317119a3",
    }
)
DEMO_COHORT_KEYS = frozenset({"p_101", "p_103"})
PUBLISHABLE_KEYS = SHOWCASE_KEYS | DEMO_COHORT_KEYS


def index_decision(patient_key: str, *, source: str, presidio_ok: bool) -> str:
    """candidate, withhold, or quarantine. candidate still needs stores_agree before release."""
    if not presidio_ok:
        return "quarantine"
    if source == "raw":
        return "candidate" if patient_key in SHOWCASE_KEYS else "withhold"
    if source == "example":
        return "candidate" if patient_key in SHOWCASE_KEYS else "withhold"
    if source == "cohort":
        return "candidate" if patient_key in PUBLISHABLE_KEYS else "withhold"
    return "withhold"


def stores_agree(
    *,
    sanitized_ref: str | None,
    deid_version: str | None,
    points: list[dict[str, Any]],
    ledger: str,
) -> bool:
    """Postgres row, Qdrant points, and the ledger all say this note may be read."""
    if ledger != "published":
        return False
    if not sanitized_ref or not deid_version or not points:
        return False
    return all(p.get("id") and (p.get("payload") or {}).get("deid_version") for p in points)


def chunk_visible(chunk: dict[str, Any]) -> bool:
    """Drop indexed leftovers. Rows with no patient key are not a Synthea bulk load."""
    key = chunk.get("patient_key")
    if not key:
        return True
    return str(key) in PUBLISHABLE_KEYS
