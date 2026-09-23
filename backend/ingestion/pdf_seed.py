#!/usr/bin/env python3
"""Write real PDF bytes for sanitized notes and radiology reports into MinIO."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_notes import DEMO_NOTE_BODIES, DEMO_NOTE_HINTS  # noqa: E402
from imaging_catalog import STUDIES, pdf_object_key  # noqa: E402
from patient360.clinical_view import clean_synthea_note  # noqa: E402
from patient360.deid import DEID_VERSION, hints_from_mapping, sanitize  # noqa: E402
from patient360.tools.stores import MinioObjects  # noqa: E402

DEFAULT_ENV_FILE = ROOT / "backend" / "deploy" / "patient360" / ".env"
DEFAULT_EXAMPLES = ROOT / ".data" / "clinical-examples-notes.json"

DEMO_NOTES: tuple[tuple[str, str, str], ...] = (
    ("p101-psych-consult-2026-09-12", "p_101", "Consult note"),
    ("p101-admission-2026-09-10", "p_101", "Discharge summary"),
    ("p103-cardiology-2026-05-20", "p_103", "History and physical note"),
)


def _escape(text: str) -> str:
    raw = text.encode("latin-1", errors="replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 90) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= width:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_pdf(title: str, body: str) -> bytes:
    """Minimal PDF 1.4. The bytes start with %PDF- so the viewer opens them."""
    lines = _wrap(title, 80) + [""] + _wrap(body)
    page_lines = 42
    pages = [lines[index : index + page_lines] for index in range(0, max(len(lines), 1), page_lines)]
    font_id = 3 + len(pages) * 2
    objects: list[bytes] = [b""]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for index, chunk in enumerate(pages):
        commands = ["BT", "/F1 11 Tf", "54 740 Td"]
        for line_index, line in enumerate(chunk):
            if line_index:
                commands.append("0 -16 Td")
            commands.append(f"({_escape(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        content_id = 4 + index * 2
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
            ).encode()
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects[1:], start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        (
            f"trailer << /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(out)


def sanitized_demo_text(note_id: str) -> str:
    hints = hints_from_mapping(**DEMO_NOTE_HINTS[note_id])
    result = sanitize(DEMO_NOTE_BODIES[note_id], hints)
    if not result.ok:
        raise RuntimeError(f"{note_id} still contains identifiers")
    return result.text


def sanitized_example_text(row: dict[str, Any]) -> str:
    hints = hints_from_mapping(
        names=tuple(row.get("names") or ()),
        dob_strings=tuple(row.get("dob_strings") or ()),
        mrns=tuple(row.get("mrns") or ()),
        phones=tuple(row.get("phones") or ()),
        source_ids=tuple(row.get("source_ids") or ()),
    )
    result = sanitize(str(row.get("text") or ""), hints)
    if not result.ok:
        raise RuntimeError(f"{row.get('note_id')} still contains identifiers")
    return clean_synthea_note(result.text)


def _when(raw: str) -> datetime:
    match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", raw)
    if not match:
        return datetime(2026, 9, 22, tzinfo=timezone.utc)
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)


def _jsonb(value: dict[str, Any]):
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _minio(env: dict[str, str]) -> MinioObjects:
    url = env.get("PATIENT360_MINIO_URL", "http://127.0.0.1:9000")
    if url.startswith("http://minio"):
        url = "http://127.0.0.1:9000"
    access = env.get("PATIENT360_MINIO_ACCESS_KEY") or env.get("PATIENT360_MINIO_USER", "patient360")
    secret = env.get("PATIENT360_MINIO_SECRET_KEY") or env.get("PATIENT360_MINIO_PASSWORD", "")
    return MinioObjects(url, access, secret)


def _dsn(env: dict[str, str], explicit: str | None) -> str:
    if explicit:
        return explicit
    if env.get("PATIENT360_WORKER_DSN"):
        return env["PATIENT360_WORKER_DSN"]
    return (
        f"postgres://p360_worker:{env.get('PATIENT360_WORKER_PASSWORD', 'patient360-worker-dev')}"
        f"@{env.get('PATIENT360_PG_HOST', '127.0.0.1')}:{env.get('PATIENT360_PG_PORT', '5432')}/fhir"
    )


def _upsert_note(
    conn,
    *,
    source_id: str,
    patient_key: str,
    type_display: str,
    authored_at: datetime | None,
    object_key: str,
    confidentiality: str,
    internal: bool,
) -> None:
    updated = conn.execute(
        "UPDATE clinical.notes SET sanitized_ref = %s, published = true, deid_version = %s "
        "WHERE source_id = %s RETURNING id",
        (object_key, DEID_VERSION, source_id),
    ).fetchone()
    if updated:
        return
    encounter = conn.execute(
        "SELECT id FROM clinical.encounters WHERE patient_key = %s "
        "ORDER BY started_at DESC NULLS LAST LIMIT 1",
        (patient_key,),
    ).fetchone()
    conn.execute(
        "INSERT INTO clinical.notes ("
        "source_id, patient_key, encounter_id, status, type_code, type_system, type_display, "
        "category, authored_at, sanitized_ref, internal, provenance, published, deid_version, "
        "confidentiality, sensitivity, resource"
        ") VALUES ("
        "%s, %s, %s, 'current', '34117-2', 'http://loinc.org', %s, "
        "'clinical-note', %s, %s, %s, 'clinical', true, %s, %s, %s, %s"
        ")",
        (
            source_id,
            patient_key,
            encounter[0] if encounter else None,
            type_display,
            authored_at,
            object_key,
            internal,
            DEID_VERSION,
            confidentiality,
            [],
            _jsonb(
                {
                    "resourceType": "DocumentReference",
                    "status": "current",
                    "type": {"coding": [{"system": "http://loinc.org", "code": "34117-2", "display": type_display}]},
                    "category": [{"coding": [{"code": "clinical-note"}]}],
                }
            ),
        ),
    )


async def _store(client: MinioObjects, items: list[tuple[str, bytes]]) -> None:
    for key, payload in items:
        await client.put("reports", key, payload, content_type="application/pdf")


def seed(*, dsn: str, client: MinioObjects, examples_path: Path) -> dict[str, Any]:
    import psycopg

    items: list[tuple[str, bytes]] = []
    note_rows: list[dict[str, Any]] = []
    for note_id, patient_key, title in DEMO_NOTES:
        text = sanitized_demo_text(note_id)
        key = pdf_object_key(patient_key, note_id)
        items.append((key, render_pdf(title, text)))
        note_rows.append(
            {
                "source_id": f"seed-demo/DocumentReference/{note_id}",
                "patient_key": patient_key,
                "type_display": title,
                "authored_at": None,
                "object_key": key,
                "confidentiality": "V" if "psych" in note_id else "N",
                "internal": "psych" in note_id,
                "raw": "",
            }
        )
    if examples_path.is_file():
        examples = json.loads(examples_path.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"missing sanitized-note source {examples_path}")
    for row in examples:
        title = str(row.get("example") or "Clinical note").replace("-", " ").capitalize()
        text = sanitized_example_text(row)
        key = pdf_object_key(str(row["patient_key"]), str(row["note_id"]))
        items.append((key, render_pdf(title, text)))
        note_rows.append(
            {
                "source_id": f"seed-demo/DocumentReference/{row['note_id']}",
                "patient_key": row["patient_key"],
                "type_display": title,
                "authored_at": _when(str(row.get("text") or "")),
                "object_key": key,
                "confidentiality": "N",
                "internal": False,
                "raw": str(row.get("text") or ""),
            }
        )
    for study in STUDIES:
        items.append((study.report_ref, render_pdf(study.procedure_display, study.conclusion_text)))

    asyncio.run(_store(client, items))
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            for row in note_rows:
                _upsert_note(
                    conn,
                    source_id=row["source_id"],
                    patient_key=row["patient_key"],
                    type_display=row["type_display"],
                    authored_at=row["authored_at"],
                    object_key=row["object_key"],
                    confidentiality=row["confidentiality"],
                    internal=row["internal"],
                )
            for study in STUDIES:
                conn.execute(
                    "UPDATE clinical.diagnostic_reports SET report_ref = %s WHERE source_id = %s",
                    (study.report_ref, study.report_source),
                )
    return {"ok": True, "objects": [key for key, _payload in items]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    ap.add_argument("--dsn")
    ap.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    args = ap.parse_args(argv)
    from seed_demo import load_env_file

    env = {**load_env_file(args.env_file), **os.environ}
    result = seed(dsn=_dsn(env, args.dsn), client=_minio(env), examples_path=args.examples)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
