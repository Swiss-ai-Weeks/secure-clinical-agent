#!/usr/bin/env python3
"""Stretch: TCIA → header strip → Orthanc. Not on the critical demo path."""

from __future__ import annotations

import json


def plan() -> dict:
    return {
        "status": "stretch",
        "steps": [
            "Download one TCIA study under the ingest compose profile",
            "pydicom header strip + pydeface before Orthanc C-STORE",
            "Set clinical.studies.orthanc_id; serve pixels only via /media/{signed}",
            "OHIF talks to the image auth proxy, never to Orthanc",
            "VISTA-3D SEG overlays inherit the study gate",
            "MedGemma enrichment is optional PDP-gated text",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(plan(), indent=2))
