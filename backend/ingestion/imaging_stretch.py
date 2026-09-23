#!/usr/bin/env python3
"""Imaging ingest: synthetic DICOM → Orthanc → optional MedGemma / VISTA-3D."""

from __future__ import annotations

import json
import sys

from dicom_seed import main as seed_main
from imaging_enrich import main as enrich_main


def plan() -> dict:
    return {
        "status": "wired",
        "seed": "backend/ingestion/dicom_seed.py",
        "enrich": "backend/ingestion/imaging_enrich.py",
        "patients": ["p_101", "p_102", "p_103"],
        "notes": [
            "Live pixels are retagged public-domain DICOM; ellipse pixels stay in offline tests",
            "VISTA-3D and MedGemma stay on Compose profile ingest, GPU 0",
            "Dashboard pixels go through /media/{signed}; tools stay report-text",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["plan"]:
        print(json.dumps(plan(), indent=2))
        return 0
    if argv[:1] == ["enrich"]:
        return enrich_main(argv[1:])
    return seed_main(argv[1:] if argv[:1] == ["seed"] else argv)


if __name__ == "__main__":
    sys.exit(main())
