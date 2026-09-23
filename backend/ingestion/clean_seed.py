#!/usr/bin/env python3
"""Remove Synthea social/survey rows from the clinical seed.

The FHIR volume keeps patients and encounters. This deletes observation
categories that are not labs/vitals and Condition rows that are SDOH
findings, on opaque Synthea keys only (length > 8). Demo keys p_101–p_205
are not touched. Run as the fhir_app owner; p360_worker has no DELETE.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from patient360.clinical_view import CLINICAL_CONDITION_PATTERN  # noqa: E402


def statements() -> list[str]:
    return [
        "DELETE FROM clinical.observations WHERE category IN ('survey', 'social-history')",
        (
            "DELETE FROM clinical.observations "
            "WHERE length(patient_key) > 8 "
            "AND category NOT IN ('laboratory', 'vital-signs')"
        ),
        (
            "DELETE FROM clinical.conditions "
            "WHERE length(patient_key) > 8 "
            f"AND display !~* '{CLINICAL_CONDITION_PATTERN}'"
        ),
    ]


def preview_sql() -> list[str]:
    return [
        "SELECT category, COUNT(*) FROM clinical.observations "
        "WHERE category IN ('survey', 'social-history') GROUP BY 1 ORDER BY 1",
        (
            "SELECT COUNT(*) AS social_conditions FROM clinical.conditions "
            "WHERE length(patient_key) > 8 "
            f"AND display !~* '{CLINICAL_CONDITION_PATTERN}'"
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    body = {"preview": preview_sql(), "apply": statements()}
    if not args.apply:
        print(json.dumps(body, indent=2))
        return 0
    print(";\n".join(statements()) + ";")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
