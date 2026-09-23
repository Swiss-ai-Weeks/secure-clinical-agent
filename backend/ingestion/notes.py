#!/usr/bin/env python3
"""Sanitize, chunk, embed, and publish notes. Never index raw-notes.jsonl.

First cohort: authored p_101/p_103 demo notes, optional Synthea demo examples,
and an isolated evaluation corpus (note_chunks_eval).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID, uuid5

NOTES_NAMESPACE = UUID("3c0a1f5e-8b2d-4e91-9c47-2a6f0d8e1b33")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = ROOT / "app"
for path in (str(HERE), str(APP)):
    if path not in sys.path:
        sys.path.insert(0, path)

from demo_notes import DEMO_NOTE_BODIES, DEMO_NOTE_HINTS  # noqa: E402
from note_vectors import (  # noqa: E402
    ModelTokenizer,
    VectorPreparationError,
    chunk_note,
    digest,
    embed_inputs,
    input_text,
)

from patient360.deid import (  # noqa: E402
    IdentityHints,
    SanitizeResult,
    hints_from_mapping,
    preserve_attack_passage,
    sanitize,
)
from patient360.publication import index_decision  # noqa: E402

COLLECTION = "note_chunks"
EVAL_COLLECTION = "note_chunks_eval"
TOKENIZER_PATH = ""
EMBED_URL = ""
EMBED_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"


class NotesError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _load_tokenizer(path: str) -> ModelTokenizer:
    return ModelTokenizer(path)


def _tokenizer() -> ModelTokenizer:
    return _load_tokenizer(TOKENIZER_PATH or os.environ.get("PATIENT360_EMBED_TOKENIZER", ""))


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


def prepare_note(
    note_id: str, raw: str, hints: IdentityHints | None = None, *, tokenizer: ModelTokenizer | None = None
) -> dict[str, Any]:
    result = sanitize_body(note_id, raw, hints)
    if not result.ok:
        return {
            "note_id": note_id,
            "ok": False,
            "canary_hits": result.canary_hits,
            "deid_version": result.deid_version,
        }
    tokenizer = tokenizer or _tokenizer()
    try:
        chunks = chunk_note(result.text, tokenizer, note_id=note_id, deid_version=result.deid_version)
    except VectorPreparationError as error:
        return {"note_id": note_id, "ok": False, "reason": str(error), "deid_version": result.deid_version}
    if not chunks:
        return {"note_id": note_id, "ok": False, "reason": "empty_sanitized_note"}
    return {
        "note_id": note_id,
        "ok": True,
        "text": result.text,
        "deid_version": result.deid_version,
        "stage": "chunked",
        "published": False,
        "tokenizer_sha256": tokenizer.sha256,
        "chunk_policy_id": tokenizer.policy_id,
        "preparation_id": digest(
            {
                "note_id": note_id,
                "text": result.text,
                "deid_version": result.deid_version,
                "chunk_policy_id": tokenizer.policy_id,
            }
        ),
        "chunks": chunks,
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
    with urlopen(req, timeout=120) as resp:
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


def embed_texts(
    embed_url: str,
    model: str,
    texts: list[str],
    *,
    input_type: str = "passage",
    batch_size: int = 8,
    tokenizer: ModelTokenizer | None = None,
) -> list[list[float]]:
    """Passage embeddings, eight texts at a time. Fail closed; never truncate."""
    if not embed_url:
        raise NotesError("embedding_endpoint_required")
    try:
        return embed_inputs(
            texts,
            tokenizer or _tokenizer(),
            lambda body: _http_json("POST", f"{embed_url.rstrip('/')}/v1/embeddings", body, ""),
            model=model,
            mode=input_type,
            batch_size=batch_size,
        )
    except VectorPreparationError as error:
        raise NotesError(str(error)) from None


def embed_prepared(
    prepared: dict[str, Any], embed_url: str, *, tokenizer: ModelTokenizer | None = None
) -> dict[str, Any]:
    """Revalidate the prepared artifact and return vectors without store writes."""
    if prepared.get("ok") is not True or not prepared.get("deid_version"):
        raise NotesError("note_not_admitted")
    tokenizer = tokenizer or _tokenizer()
    if prepared.get("chunk_policy_id") != tokenizer.policy_id:
        raise NotesError("chunk_policy_mismatch")
    if prepared.get("tokenizer_sha256") != tokenizer.sha256:
        raise NotesError("tokenizer_identity_mismatch")
    identity = digest(
        {
            "note_id": prepared["note_id"],
            "text": prepared["text"],
            "deid_version": prepared["deid_version"],
            "chunk_policy_id": tokenizer.policy_id,
        }
    )
    if prepared.get("preparation_id") != identity:
        raise NotesError("preparation_identity_mismatch")
    expected = chunk_note(
        prepared["text"], tokenizer, note_id=prepared["note_id"], deid_version=prepared["deid_version"]
    )
    if not expected or prepared.get("chunks") != expected:
        raise NotesError("prepared_chunks_mismatch")
    vectors = embed_texts(embed_url, EMBED_MODEL, [input_text(c) for c in expected], tokenizer=tokenizer)
    return {
        **prepared,
        "stage": "embedded",
        "published": False,
        "embedding_model": EMBED_MODEL,
        "chunks": [{**chunk, "vector": vector} for chunk, vector in zip(expected, vectors, strict=True)],
    }


def save_prepared(path: Path, artifact: dict[str, Any]) -> None:
    """Atomic owner-only artifact; failed inference never writes an embedded artifact."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".prepared-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(artifact, handle, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


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
    point: dict[str, Any] = {
        "id": chunk.get("point_id")
        or str(uuid5(NOTES_NAMESPACE, str(chunk.get("preparation_chunk_id") or f"{note_id}:{chunk.get('chunk_index')}"))),
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
            "text": chunk.get("text") or "",
            "heading": chunk.get("heading") or chunk.get("heading_context") or "",
            "start": chunk.get("start", chunk.get("start_offset")),
            "end": chunk.get("end", chunk.get("end_offset")),
        },
    }
    if chunk.get("vector"):
        point["vector"] = chunk["vector"]
    return point


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


def points_for_prepared(
    prepared: dict[str, Any], meta: dict[str, Any], *, published: bool
) -> list[dict[str, Any]]:
    if not prepared.get("ok"):
        raise NotesError(f"cannot publish {prepared.get('note_id')}")
    chunks = list(prepared["chunks"])
    if EMBED_URL:
        vectors = embed_texts(EMBED_URL, EMBED_MODEL, [input_text(c) if "heading_context" in c else c["text"] for c in chunks])
        if len(vectors) != len(chunks):
            raise NotesError("embed count mismatch")
        chunks = [{**chunk, "vector": vector} for chunk, vector in zip(chunks, vectors, strict=True)]
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
        for chunk in chunks
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


def _ledger_record(note_id: str, record: dict[str, Any], checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    if checkpoint is not None and note_id:
        checkpoint.setdefault("notes", {})[note_id] = record
    return record


def publish_prepared(
    prepared: dict[str, Any],
    meta: dict[str, Any],
    *,
    qdrant_url: str,
    api_key: str,
    collection: str = COLLECTION,
    checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write unpublished points, then flip published only when Postgres, Qdrant, and the ledger agree."""
    note_id = str(prepared.get("note_id") or "")
    decision = index_decision(
        str(meta.get("patient_key") or ""),
        source=str(meta.get("source") or "cohort"),
        presidio_ok=bool(prepared.get("ok")),
    )
    if decision != "candidate":
        return _ledger_record(
            note_id,
            {"ok": bool(prepared.get("ok")), "published": False, "ledger": decision, "points": []},
            checkpoint,
        )
    prior = (checkpoint or {}).get("notes", {}).get(note_id) or {}
    if prior.get("published") and prior.get("ledger") == "published":
        return prior
    unpublished = points_for_prepared(prepared, meta, published=False)
    upsert_chunks(qdrant_url, api_key, collection, unpublished)
    if not can_publish(
        sanitized_ref=f"notes/{meta['patient_key']}/{note_id}.txt",
        deid_version=prepared["deid_version"],
        points=unpublished,
    ):
        record = {
            "ok": True,
            "published": False,
            "ledger": "staged",
            "points": [p["id"] for p in unpublished],
        }
        return _ledger_record(note_id, record, checkpoint)
    published = points_for_prepared(prepared, meta, published=True)
    upsert_chunks(qdrant_url, api_key, collection, published)
    record = {
        "ok": True,
        "published": True,
        "ledger": "published",
        "points": [p["id"] for p in published],
        "sanitized_ref": f"notes/{meta['patient_key']}/{note_id}.txt",
        "deid_version": prepared["deid_version"],
    }
    return _ledger_record(note_id, record, checkpoint)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare and embed unpublished note artifacts")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true", help="prepare without model or store calls")
    mode.add_argument("--embed-only", action="store_true", help="embed into restricted unpublished artifacts")
    parser.add_argument(
        "--output", type=Path, help="restricted directory for versioned preparation artifacts"
    )
    parser.add_argument("--qdrant-url", default=os.environ.get("PATIENT360_QDRANT_URL", ""))
    parser.add_argument("--qdrant-key", default=os.environ.get("PATIENT360_QDRANT_API_KEY", ""))
    parser.add_argument("--raw-notes", type=Path, help="remaining Synthea raw-notes.jsonl")
    parser.add_argument("--mapping", type=Path, help="JSON map of source patient id -> opaque patient_key")
    parser.add_argument(
        "--eval-jsonl", type=Path, help="attack/control corpus; isolated evaluation artifacts"
    )
    parser.add_argument("--checkpoint", type=Path, default=Path(".data/notes-checkpoint.json"))
    parser.add_argument("--embed-url", default=os.environ.get("PATIENT360_EMBED_URL", ""))
    parser.add_argument(
        "--embed-model",
        default=os.environ.get("PATIENT360_EMBED_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2"),
    )
    parser.add_argument("--tokenizer", default=os.environ.get("PATIENT360_EMBED_TOKENIZER", ""))
    parser.add_argument(
        "--clinical-examples",
        type=Path,
        help="JSON list of {note_id, patient_key, text, ...meta} to prepare after the first cohort",
    )
    args = parser.parse_args(argv)
    global TOKENIZER_PATH, EMBED_URL, EMBED_MODEL

    if args.embed_only and (not args.embed_url or not args.output):
        parser.error("--embed-only requires --embed-url and --output")
    if not args.tokenizer:
        default_tok = Path.home() / ".cache/nim/embed/weights/embed/tokenizer.json"
        if default_tok.is_file():
            args.tokenizer = str(default_tok)
    TOKENIZER_PATH, EMBED_URL, EMBED_MODEL = args.tokenizer, args.embed_url, args.embed_model
    _load_tokenizer.cache_clear()  # Reverify the file on every CLI invocation.
    _tokenizer()  # Fail before any preparation/model calls; no word-count fallback.
    mapping = json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping else {}
    cohort = first_cohort()
    for item in cohort:
        item["meta"] = {**FIRST_COHORT_META[item["note_id"]], "source": "cohort"}
    if args.clinical_examples:
        extra = json.loads(args.clinical_examples.read_text(encoding="utf-8"))
        for row in extra:
            hints = hints_from_mapping(
                names=tuple(row.get("names") or ()),
                dob_strings=tuple(row.get("dob_strings") or ()),
                mrns=tuple(row.get("mrns") or ()),
                phones=tuple(row.get("phones") or ()),
                source_ids=tuple(row.get("source_ids") or ()),
            )
            prepared = prepare_note(str(row["note_id"]), str(row["text"]), hints)
            prepared["meta"] = {
                "patient_key": row["patient_key"],
                "confidentiality": row.get("confidentiality") or "N",
                "sensitivity": list(row.get("sensitivity") or []),
                "internal": bool(row.get("internal")),
                "dept": row.get("dept"),
                "provenance": row.get("provenance") or "clinical",
                "source": "example",
            }
            cohort.append(prepared)
    if args.raw_notes:
        raw_rows = prepare_jsonl(load_jsonl(args.raw_notes), mapping)
        for item in raw_rows:
            if item.get("meta") is not None:
                item["meta"]["source"] = "raw"
        cohort.extend(raw_rows)
    eval_notes = prepare_eval_corpus(load_jsonl(args.eval_jsonl)) if args.eval_jsonl else []

    failed = 0
    embedded = 0
    chunks = 0
    reasons: dict[str, int] = {}
    for corpus, items in (("clinical", cohort), ("evaluation", eval_notes)):
        for item in items:
            if not item["ok"]:
                failed += 1
                reason = item.get("reason", "sanitization_failed")
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            chunks += len(item["chunks"])
            if args.output:
                save_prepared(args.output / corpus / item["preparation_id"] / "chunked.json", item)
            if args.embed_only:
                try:
                    result = embed_prepared(item, args.embed_url)
                except (NotesError, VectorPreparationError) as error:
                    failed += 1
                    reasons[str(error)] = reasons.get(str(error), 0) + 1
                    continue
                save_prepared(args.output / corpus / item["preparation_id"] / "embedded.json", result)
                embedded += 1
    published = 0
    if args.qdrant_url and not args.prepare_only and not args.embed_only:
        if failed:
            print(json.dumps({"ok": False, "failed": failed, "reasons": reasons, "published": 0}), file=sys.stderr)
            return 2
        ensure_collection(args.qdrant_url, args.qdrant_key, COLLECTION)
        state = load_checkpoint(args.checkpoint)
        for item in cohort:
            if not item.get("ok"):
                _ledger_record(
                    str(item.get("note_id") or ""),
                    {"ok": False, "published": False, "ledger": "quarantine", "points": []},
                    state,
                )
                continue
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
                if item.get("ok"):
                    upsert_chunks(
                        args.qdrant_url,
                        args.qdrant_key,
                        EVAL_COLLECTION,
                        points_for_prepared(item, item["meta"], published=True),
                    )
        print(json.dumps({"ok": True, "published": published, "notes": len(cohort), "eval": len(eval_notes)}))
        return 0

    print(
        json.dumps(
            {
                "ok": failed == 0,
                "stage": "embedded" if args.embed_only else "chunked",
                "notes": len(cohort),
                "eval": len(eval_notes),
                "chunks": chunks,
                "embedded": embedded,
                "failed": failed,
                "reasons": reasons,
                "published": published,
            },
            indent=2,
        )
    )
    return 2 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (NotesError, VectorPreparationError) as error:
        print(json.dumps({"ok": False, "reason": str(error), "published": 0}), file=sys.stderr)
        raise SystemExit(2) from None
