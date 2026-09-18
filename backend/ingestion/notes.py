#!/usr/bin/env python3
"""Sanitize, chunk, and publish notes. Never index raw-notes.jsonl.

First cohort: authored p_101/p_103 demo notes, optional Synthea demo examples,
and the isolated evaluation corpus (note_chunks_eval, never published clinically).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = ROOT / "app"
for path in (str(HERE), str(APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

from patient360.deid import (  # noqa: E402
    DEID_VERSION,
    IdentityHints,
    SanitizeResult,
    chunk_text,
    hints_from_mapping,
    preserve_attack_passage,
    sanitize,
)

from demo_notes import DEMO_NOTE_BODIES, DEMO_NOTE_HINTS  # noqa: E402

COLLECTION = "note_chunks"
EVAL_COLLECTION = "note_chunks_eval"


class NotesError(RuntimeError):
    pass


def sanitize_body(note_id: str, raw: str, hints: IdentityHints | None = None) -> SanitizeResult:
    mapped = DEMO_NOTE_HINTS.get(note_id)
    if hints is None and mapped:
        hints = hints_from_mapping(**mapped)
    result = sanitize(raw, hints)
    result.text = preserve_attack_passage(raw, result.text)
    if not result.ok:
        return result
    # Re-canary after attack-passage splice (identifiers must not return with the attack text).
    if hints:
        from patient360.deid import canary_hits

        hits = canary_hits(result.text, hints)
        result.canary_hits = hits
        result.ok = not hits
    return result


def prepare_note(note_id: str, raw: str, hints: IdentityHints | None = None) -> dict[str, Any]:
    result = sanitize_body(note_id, raw, hints)
    if not result.ok:
        return {
            "note_id": note_id,
            "ok": False,
            "canary_hits": result.canary_hits,
            "deid_version": result.deid_version,
        }
    chunks = chunk_text(result.text, note_id, deid_version=result.deid_version)
    return {
        "note_id": note_id,
        "ok": True,
        "text": result.text,
        "deid_version": result.deid_version,
        "chunks": [
            {
                "chunk_index": c.chunk_index,
                "text": c.text,
                "start": c.start,
                "end": c.end,
                "point_id": c.point_id,
            }
            for c in chunks
        ],
    }


def first_cohort() -> list[dict[str, Any]]:
    out = []
    for note_id, raw in DEMO_NOTE_BODIES.items():
        prepared = prepare_note(note_id, raw)
        out.append(prepared)
    return out


def _http_json(method: str, url: str, body: dict[str, Any] | None, api_key: str) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("api-key", api_key)
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def ensure_collection(qdrant_url: str, api_key: str, name: str) -> None:
    info_url = f"{qdrant_url.rstrip('/')}/collections/{quote(name)}"
    try:
        info = _http_json("GET", info_url, None, api_key)
        params = ((info or {}).get("result") or {}).get("config", {}).get("params", {}).get("vectors", {})
        size = params.get("size")
        if size not in (None, 2048):
            raise NotesError(f"collection {name} has incompatible vector size {size}")
    except Exception as exc:
        if isinstance(exc, NotesError):
            raise
        _http_json(
            "PUT",
            info_url,
            {"vectors": {"size": 2048, "distance": "Cosine"}},
            api_key,
        )
    for field in ("patient_key", "confidentiality", "published"):
        _http_json(
            "PUT",
            f"{info_url}/index",
            {"field_name": field, "field_schema": "keyword"},
            api_key,
        )


def upsert_chunks(
    qdrant_url: str,
    api_key: str,
    collection: str,
    points: list[dict[str, Any]],
) -> None:
    if not points:
        return
    _http_json(
        "PUT",
        f"{qdrant_url.rstrip('/')}/collections/{quote(collection)}/points?wait=true",
        {"points": points},
        api_key,
    )


FIRST_COHORT_META: dict[str, dict[str, Any]] = {
    "p101-psych-consult-2026-09-12": {
        "patient_key": "p_101",
        "confidentiality": "V",
        "sensitivity": ["PSY"],
        "internal": True,
        "dept": "psych",
        "provenance": "clinical",
    },
    "p101-admission-2026-09-10": {
        "patient_key": "p_101",
        "confidentiality": "N",
        "sensitivity": [],
        "internal": False,
        "dept": "medicine",
        "provenance": "clinical",
    },
    "p103-cardiology-2026-05-20": {
        "patient_key": "p_103",
        "confidentiality": "N",
        "sensitivity": [],
        "internal": False,
        "dept": "cardiology",
        "provenance": "clinical",
    },
}


def payload_for(
    chunk: dict[str, Any],
    *,
    patient_key: str,
    note_id: str,
    confidentiality: str,
    sensitivity: list[str],
    dept: str | None,
    published: bool,
    provenance: str,
    deid_version: str,
    internal: bool = False,
) -> dict[str, Any]:
    required = (patient_key, note_id, confidentiality, deid_version)
    if not all(required):
        raise NotesError("missing ACL metadata")
    return {
        "id": chunk["point_id"],
        "payload": {
            "patient_key": patient_key,
            "note_id": note_id,
            "confidentiality": confidentiality,
            "sensitivity": sensitivity,
            "dept": dept,
            "published": published,
            "internal": internal,
            "provenance": provenance,
            "chunk_index": chunk["chunk_index"],
            "deid_version": deid_version,
            "text": chunk["text"],
        },
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"notes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def can_publish(*, sanitized_ref: str | None, deid_version: str | None, points: list[dict[str, Any]]) -> bool:
    """Cross-store gate: sanitized row + every Qdrant point present. Callers flip published last."""
    if not sanitized_ref or not deid_version or not points:
        return False
    return all(p.get("id") and (p.get("payload") or {}).get("deid_version") for p in points)


def points_for_prepared(prepared: dict[str, Any], meta: dict[str, Any], *, published: bool) -> list[dict[str, Any]]:
    if not prepared.get("ok"):
        raise NotesError(f"cannot publish {prepared.get('note_id')}")
    return [
        payload_for(
            chunk,
            patient_key=meta["patient_key"],
            note_id=prepared["note_id"],
            confidentiality=meta["confidentiality"],
            sensitivity=list(meta.get("sensitivity") or []),
            dept=meta.get("dept"),
            published=published,
            provenance=meta.get("provenance") or "clinical",
            deid_version=prepared["deid_version"],
            internal=bool(meta.get("internal")),
        )
        for chunk in prepared["chunks"]
    ]


def prepare_jsonl(
    rows: list[dict[str, Any]],
    mapping: dict[str, str],
    *,
    default_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Sanitize raw-notes.jsonl rows. mapping: source patient id -> opaque patient_key."""
    out: list[dict[str, Any]] = []
    base = default_meta or {
        "confidentiality": "N",
        "sensitivity": [],
        "internal": False,
        "dept": None,
        "provenance": "clinical",
    }
    for row in rows:
        source_patient = str(row.get("patient_id") or row.get("source_patient_id") or "")
        note_id = str(row.get("note_id") or row.get("document_id") or row.get("id") or "")
        raw = str(row.get("text") or row.get("note") or "")
        key = mapping.get(source_patient) or mapping.get(note_id)
        if not key or not note_id or not raw:
            out.append({"note_id": note_id or source_patient, "ok": False, "canary_hits": ["unmapped"]})
            continue
        hints = hints_from_mapping(
            names=tuple(row.get("names") or ()),
            dob_strings=tuple(row.get("dob_strings") or ()),
            mrns=tuple(row.get("mrns") or ()),
            phones=tuple(row.get("phones") or ()),
            source_ids=tuple(x for x in (row.get("source_id"), note_id) if x),
        )
        prepared = prepare_note(note_id, raw, hints)
        prepared["meta"] = {**base, "patient_key": key}
        out.append(prepared)
    return out


def prepare_eval_corpus(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize attack/control notes for note_chunks_eval only."""
    out: list[dict[str, Any]] = []
    for row in rows:
        note_id = str(row.get("note_id") or row.get("id") or f"eval-{len(out)}")
        raw = str(row.get("text") or row.get("note") or "")
        prepared = prepare_note(note_id, raw, IdentityHints(source_ids=(note_id,)))
        prepared["meta"] = {
            "patient_key": str(row.get("patient_key") or "p_eval"),
            "confidentiality": "N",
            "sensitivity": ["EVAL"],
            "internal": False,
            "dept": "eval",
            "provenance": "adversarial",
        }
        out.append(prepared)
    return out


def publish_prepared(
    prepared: dict[str, Any],
    meta: dict[str, Any],
    *,
    qdrant_url: str,
    api_key: str,
    collection: str = COLLECTION,
    checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write unpublished points, then flip published only when the set is complete."""
    note_id = prepared["note_id"]
    prior = (checkpoint or {}).get("notes", {}).get(note_id) or {}
    if prior.get("published"):
        return prior
    unpublished = points_for_prepared(prepared, meta, published=False)
    upsert_chunks(qdrant_url, api_key, collection, unpublished)
    if not can_publish(
        sanitized_ref=f"notes/{meta['patient_key']}/{note_id}.txt",
        deid_version=prepared["deid_version"],
        points=unpublished,
    ):
        record = {"ok": True, "published": False, "points": [p["id"] for p in unpublished]}
        if checkpoint is not None:
            checkpoint.setdefault("notes", {})[note_id] = record
        return record
    published = points_for_prepared(prepared, meta, published=True)
    upsert_chunks(qdrant_url, api_key, collection, published)
    record = {"ok": True, "published": True, "points": [p["id"] for p in published]}
    if checkpoint is not None:
        checkpoint.setdefault("notes", {})[note_id] = record
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanitize, checkpoint, and publish notes")
    parser.add_argument("--prepare-only", action="store_true", help="print JSON; do not write stores")
    parser.add_argument("--qdrant-url", default="")
    parser.add_argument("--qdrant-key", default="")
    parser.add_argument("--raw-notes", type=Path, help="remaining Synthea raw-notes.jsonl")
    parser.add_argument("--mapping", type=Path, help="JSON map of source patient id -> opaque patient_key")
    parser.add_argument("--eval-jsonl", type=Path, help="attack/control corpus; writes note_chunks_eval")
    parser.add_argument("--checkpoint", type=Path, default=Path(".data/notes-checkpoint.json"))
    args = parser.parse_args(argv)

    mapping = json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping else {}
    cohort = first_cohort()
    for item in cohort:
        item["meta"] = FIRST_COHORT_META[item["note_id"]]
    if args.raw_notes:
        cohort.extend(prepare_jsonl(load_jsonl(args.raw_notes), mapping))
    eval_notes = prepare_eval_corpus(load_jsonl(args.eval_jsonl)) if args.eval_jsonl else []

    failed = [n for n in cohort if not n["ok"]]
    if failed:
        print(json.dumps({"ok": False, "failed": [n["note_id"] for n in failed]}), file=sys.stderr)
        return 2
    if args.prepare_only or not args.qdrant_url:
        print(
            json.dumps(
                {
                    "ok": True,
                    "deid_version": DEID_VERSION,
                    "notes": len(cohort),
                    "eval": len(eval_notes),
                    "published": 0,
                },
                indent=2,
            )
        )
        return 0

    ensure_collection(args.qdrant_url, args.qdrant_key, COLLECTION)
    state = load_checkpoint(args.checkpoint)
    published = 0
    for item in cohort:
        record = publish_prepared(
            item,
            item["meta"],
            qdrant_url=args.qdrant_url,
            api_key=args.qdrant_key,
            checkpoint=state,
        )
        published += int(bool(record.get("published")))
    save_checkpoint(args.checkpoint, state)

    if eval_notes:
        ensure_collection(args.qdrant_url, args.qdrant_key, EVAL_COLLECTION)
        for item in eval_notes:
            if not item["ok"]:
                continue
            # Eval points stay in the isolated collection and are never clinical-published.
            upsert_chunks(
                args.qdrant_url,
                args.qdrant_key,
                EVAL_COLLECTION,
                points_for_prepared(item, item["meta"], published=True),
            )

    print(json.dumps({"ok": True, "published": published, "notes": len(cohort), "eval": len(eval_notes)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
