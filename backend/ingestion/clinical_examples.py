"""Load the three approved Synthea demonstration notes for publication."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from patient360.clinical_view import clean_synthea_name  # noqa: E402
BATCH = "71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36"
EVIDENCE = ROOT / ".data/clinical-demo" / BATCH / "candidate-evidence.json"
REGISTRY = ROOT / ".data/identity/registry.sqlite"
SOURCE = ROOT / ".data/ingestion" / BATCH


def _source(kind: str, value: str) -> str:
    return value if value.startswith(f"{kind}/") else f"{kind}/{value}"


def _resource(bundle: dict[str, Any], kind: str, resource_id: str) -> dict[str, Any]:
    want = _source(kind, resource_id)
    return next(
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == kind
        and _source(kind, entry["resource"]["id"]) == want
    )


def _official_name(patient: dict[str, Any]) -> tuple[str, str]:
    names = list(patient.get("name") or [])
    chosen = next((n for n in names if n.get("use") in (None, "official", "usual")), names[0] if names else {})
    given = " ".join(str(part) for part in (chosen.get("given") or []) if part)
    family = str(chosen.get("family") or "")
    return given, family


def _identity_and_hints(patient: dict[str, Any], *, patient_key: str, source_ids: tuple[str, ...]) -> dict[str, Any]:
    given, family = _official_name(patient)
    display_given, display_family = clean_synthea_name(given), clean_synthea_name(family)
    full = " ".join(part for part in (given, family) if part)
    birth = str(patient.get("birthDate") or "")
    phones = [str(t["value"]) for t in (patient.get("telecom") or []) if t.get("system") == "phone" and t.get("value")]
    mrns = [str(i["value"]) for i in (patient.get("identifier") or []) if i.get("value")]
    names = tuple(part for part in (full, given, family) if part)
    return {
        "identity": {
            "given_name": display_given,
            "family_name": display_family,
            "birth_date": birth,
            "sex": str(patient.get("gender") or "unknown"),
            "mrn": mrns[0] if mrns else None,
            "phone": phones[0] if phones else None,
        },
        "names": list({part for part in (*names, display_given, display_family, f"{display_given} {display_family}".strip()) if part}),
        "dob_strings": [birth] if birth else [],
        "mrns": mrns,
        "phones": phones,
        "source_ids": list(source_ids),
        "patient_key": patient_key,
    }


def load_examples(
    evidence_path: Path = EVIDENCE,
    registry_path: Path = REGISTRY,
    batch_dir: Path = SOURCE,
) -> list[dict[str, Any]]:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    registry = sqlite3.connect(registry_path)
    out: list[dict[str, Any]] = []
    for candidate in evidence.get("candidates") or []:
        source_patient = _source("Patient", candidate["source_patient_id"])
        row = registry.execute("SELECT opaque FROM identities WHERE source=?", (source_patient,)).fetchone()
        if not row:
            raise RuntimeError(f"unmapped {source_patient}")
        patient_key = row[0]
        bundle_path = ROOT / candidate["bundle"]
        if not bundle_path.exists():
            bundle_path = batch_dir / candidate["bundle"]
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        patient = _resource(bundle, "Patient", candidate["source_patient_id"])
        doc_id = _source("DocumentReference", candidate["document"]["resource_id"])
        resource = _resource(bundle, "DocumentReference", candidate["document"]["resource_id"])
        raw = base64.b64decode(resource["content"][0]["attachment"]["data"]).decode("utf-8")
        note_id = f"{patient_key}-{candidate['alias']}"
        meta = _identity_and_hints(
            patient,
            patient_key=patient_key,
            source_ids=(source_patient, doc_id, note_id),
        )
        out.append(
            {
                "note_id": note_id,
                "patient_key": patient_key,
                "example": candidate["alias"],
                "text": raw,
                "confidentiality": "N",
                "sensitivity": [],
                "internal": False,
                "dept": "synthea",
                "provenance": "clinical",
                "names": meta["names"],
                "dob_strings": meta["dob_strings"],
                "mrns": meta["mrns"],
                "phones": meta["phones"],
                "source_ids": meta["source_ids"],
                "identity": meta["identity"],
                "observation_codes": [str(o.get("code") or "") for o in (candidate.get("observations") or [])],
            }
        )
    return out


def _vault_write(url: str, token: str, mount: str, path: str, data: dict[str, Any]) -> None:
    import json as _json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"{url.rstrip('/')}/v1/{mount.strip('/')}/data/linkage/{path}",
        data=_json.dumps({"data": data}, ensure_ascii=False).encode("utf-8"),
        headers={"X-Vault-Token": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise SystemExit(f"vault write returned {resp.status}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"vault write returned {exc.code}") from exc


def register_vault(rows: list[dict[str, Any]]) -> int:
    """Write banner identities for the three examples. Worker token only."""
    url = os.environ.get("PATIENT360_LINKAGE_URL", "http://127.0.0.1:8200")
    token = os.environ.get("PATIENT360_LINKAGE_WORKER_TOKEN", "")
    mount = os.environ.get("PATIENT360_LINKAGE_MOUNT", "secret")
    if not token:
        raise SystemExit("PATIENT360_LINKAGE_WORKER_TOKEN is required to register identities")
    records = {row["patient_key"]: row["identity"] for row in rows if row.get("identity")}
    for patient_key, record in records.items():
        _vault_write(url, token, mount, f"identity/{patient_key}", {"patient_key": patient_key, **record})
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(".data/clinical-examples-notes.json"))
    parser.add_argument("--keys-only", action="store_true")
    parser.add_argument("--register-vault", action="store_true")
    args = parser.parse_args(argv)
    rows = load_examples()
    if args.keys_only:
        print(
            json.dumps(
                {
                    "patient_keys": [r["patient_key"] for r in rows],
                    "examples": [r["example"] for r in rows],
                    "note_ids": [r["note_id"] for r in rows],
                }
            )
        )
        return 0
    if args.register_vault:
        written = register_vault(rows)
        print(json.dumps({"ok": True, "vault_identities": written}))
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "notes": len(rows), "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
