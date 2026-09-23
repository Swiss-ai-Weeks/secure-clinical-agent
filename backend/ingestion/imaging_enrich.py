#!/usr/bin/env python3
"""Call MedGemma and VISTA-3D for seeded studies. Skip a model that is not up."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dicom_seed import DEFAULT_ENV_FILE, OrthancClient, _encounter_id, _orthanc_from_env
from imaging_catalog import LOINC, STUDIES, DemoStudy

_APP = Path(__file__).resolve().parents[1] / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

VISTA_PROMPT = (
    "Describe this medical image in two sentences. State only visible findings and "
    "that the image is a demonstration. Do not invent a diagnosis."
)


def _json_request(url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> tuple[int, Any, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            code = resp.getcode() or 200
    except HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        return exc.code, _maybe_json(raw), raw
    except URLError as exc:
        return 0, {"error": str(exc.reason)}, b""
    return code, _maybe_json(raw), raw


def _maybe_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def preview_png(orthanc: OrthancClient, study_id: str) -> bytes | None:
    listed = orthanc._open(f"/studies/{study_id}/instances")
    if not isinstance(listed, list) or not listed:
        return None
    instance = listed[0] if isinstance(listed[0], str) else listed[0].get("ID")
    if not instance:
        return None
    body = orthanc._open(f"/instances/{instance}/preview")
    return body if isinstance(body, (bytes, bytearray)) else None


def medgemma_describe(url: str, model: str, png: bytes) -> str:
    encoded = base64.b64encode(png).decode()
    code, body, _ = _json_request(
        f"{url.rstrip('/')}/v1/chat/completions",
        {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 220,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISTA_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        },
        timeout=120,
    )
    if code != 200 or not isinstance(body, dict):
        raise RuntimeError(f"medgemma http={code}")
    content = (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("medgemma empty")
    return content


def _orthanc_ct_files(orthanc: OrthancClient, study_id: str) -> list[bytes]:
    series = orthanc._open(f"/studies/{study_id}/series")
    if not isinstance(series, list):
        return []
    files: list[bytes] = []
    for row in series:
        if not isinstance(row, dict):
            continue
        tags = row.get("MainDicomTags") if isinstance(row.get("MainDicomTags"), dict) else {}
        if str(tags.get("Modality") or "").upper() == "SEG":
            continue
        series_id = str(row.get("ID") or "")
        if not series_id:
            continue
        instances = orthanc._open(f"/series/{series_id}/instances")
        if not isinstance(instances, list):
            continue
        for item in instances:
            ident = item if isinstance(item, str) else (item.get("ID") if isinstance(item, dict) else None)
            if not ident:
                continue
            body = orthanc._open(f"/instances/{ident}/file")
            if isinstance(body, (bytes, bytearray)):
                files.append(bytes(body))
    return files


def _delete_vista_seg(orthanc: OrthancClient, study_id: str) -> None:
    series = orthanc._open(f"/studies/{study_id}/series")
    if not isinstance(series, list):
        return
    for row in series:
        if not isinstance(row, dict):
            continue
        tags = row.get("MainDicomTags") if isinstance(row.get("MainDicomTags"), dict) else {}
        description = str(tags.get("SeriesDescription") or "")
        if str(tags.get("Modality") or "").upper() != "SEG" or "VISTA-3D" not in description:
            continue
        series_id = str(row.get("ID") or "")
        if series_id:
            orthanc._open(f"/series/{series_id}", method="DELETE")


def persist_vista_overlay(orthanc: OrthancClient, study_id: str, mask: bytes, *, classes: tuple[str, ...], study_key: str):
    from patient360.vista_overlay import build_overlay

    source = _orthanc_ct_files(orthanc, study_id)
    overlay = build_overlay(mask, source, classes=classes, study_key=study_key)
    _delete_vista_seg(orthanc, study_id)
    orthanc.store(overlay.seg_bytes)
    return overlay


def vista_segment(url: str, image_path: str, classes: tuple[str, ...]) -> bytes:
    payload: dict[str, Any] = {"image": image_path}
    if classes:
        payload["prompts"] = {"classes": list(classes)}
    code, _, raw = _json_request(
        f"{url.rstrip('/')}/v1/vista3d/inference",
        payload,
        timeout=300,
    )
    if code != 200 or not raw:
        raise RuntimeError(f"vista http={code} bytes={len(raw)}")
    return raw


def _jsonb(value: dict[str, Any]):
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _upsert_extra_report(
    seeder: Seeder, study: DemoStudy, *, source_key: str, source_id: str, display: str, text: str
) -> None:
    study_id = seeder.ids.get(f"ImagingStudy/{study.key}")
    if study_id is None:
        row = seeder.conn.execute(
            "SELECT id FROM clinical.studies WHERE source_id = %s", (study.study_source,)
        ).fetchone()
        if row:
            study_id = row[0]
            seeder.ids[f"ImagingStudy/{study.key}"] = study_id
    seeder.upsert(
        "diagnostic_reports",
        source_key,
        dict(
            source_id=source_id,
            patient_key=study.patient_key,
            encounter_id=_encounter_id(seeder, study.encounter_key),
            status="final",
            category="RAD" if study.modality == "CR" else study.modality,
            code=study.procedure_code,
            code_system=LOINC,
            display=display,
            effective_at=study.study_at,
            issued_at=study.study_at,
            conclusion_text=text,
            study_id=study_id,
            confidentiality="N",
            sensitivity=[],
            resource=_jsonb({"resourceType": "DiagnosticReport", "status": "final"}),
        ),
    )


def enrich(
    *,
    dsn: str,
    orthanc: OrthancClient,
    medgemma_url: str,
    medgemma_model: str,
    vista_url: str,
    studies: tuple[DemoStudy, ...] = STUDIES,
) -> dict[str, Any]:
    import psycopg

    from seed_demo import Seeder

    rows = []
    with psycopg.connect(dsn) as conn:
        seeder = Seeder(conn)
        with conn.transaction():
            for study in studies:
                found = conn.execute(
                    "SELECT orthanc_id FROM clinical.studies WHERE source_id = %s",
                    (study.study_source,),
                ).fetchone()
                item: dict[str, Any] = {
                    "patient_key": study.patient_key,
                    "source_id": study.study_source,
                    "orthanc_id": found[0] if found else None,
                    "medgemma": "skipped",
                    "vista": "skipped",
                }
                if found and found[0] and medgemma_url:
                    try:
                        png = preview_png(orthanc, str(found[0]))
                        if not png:
                            raise RuntimeError("no preview")
                        text = medgemma_describe(medgemma_url, medgemma_model, png)
                        _upsert_extra_report(
                            seeder,
                            study,
                            source_key=f"DiagnosticReport/{study.key}-vlm",
                            source_id=study.vlm_source,
                            display=f"{study.procedure_display} VLM description",
                            text=text,
                        )
                        item["medgemma"] = "ok"
                    except Exception as exc:
                        item["medgemma"] = f"error:{exc}"
                if found and found[0] and vista_url and study.vista_classes:
                    try:
                        raw = vista_segment(
                            vista_url, f"/data/patient360/{study.key}", study.vista_classes
                        )
                        overlay = persist_vista_overlay(
                            orthanc,
                            str(found[0]),
                            raw,
                            classes=study.vista_classes,
                            study_key=study.key,
                        )
                        item["vista_bytes"] = len(overlay.seg_bytes)
                        _upsert_extra_report(
                            seeder,
                            study,
                            source_key=f"DiagnosticReport/{study.key}-vista",
                            source_id=study.vista_source,
                            display=f"{study.procedure_display} VISTA-3D overlay",
                            text=overlay.report_text,
                        )
                        item["vista"] = "ok"
                    except Exception as exc:
                        item["vista"] = f"error:{exc}"
                rows.append(item)
    return {"ok": True, "studies": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    ap.add_argument("--dsn")
    ap.add_argument("--medgemma-url", default="")
    ap.add_argument("--vista-url", default="")
    args = ap.parse_args(argv)
    from seed_demo import load_env_file

    env = {**load_env_file(args.env_file), **os.environ}
    dsn = (
        args.dsn
        or env.get("PATIENT360_WORKER_DSN")
        or (
            f"postgres://p360_worker:{env.get('PATIENT360_WORKER_PASSWORD', 'patient360-worker-dev')}"
            f"@{env.get('PATIENT360_PG_HOST', '127.0.0.1')}:{env.get('PATIENT360_PG_PORT', '5432')}/fhir"
        )
    )
    medgemma = args.medgemma_url or env.get("PATIENT360_MEDGEMMA_URL", "http://127.0.0.1:8004")
    vista = args.vista_url or env.get("PATIENT360_VISTA_URL", "http://127.0.0.1:8003")
    if medgemma.startswith("http://medgemma"):
        medgemma = "http://127.0.0.1:8004"
    if vista.startswith("http://vista3d"):
        vista = "http://127.0.0.1:8003"
    result = enrich(
        dsn=dsn,
        orthanc=_orthanc_from_env(env),
        medgemma_url=medgemma,
        medgemma_model=env.get("PATIENT360_MEDGEMMA_MODEL", "google/medgemma-1.5-4b-it"),
        vista_url=vista,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
