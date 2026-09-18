#!/usr/bin/env python3
"""Prepare and atomically load the approved synthetic structured cohort."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from identity import NAMESPACE, Registry
import postgres
from projection import Projector
from worker import (BatchError, DEFAULT_CONFIG, ROOT, canonical, inventory, output_lock,
                    read_json, sha256, verify_batch, write_json)

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / ".data/identity/registry.sqlite"
DEFAULT_OUTPUT = ROOT / ".data/prepared"


def policy_contract():
    files = [HERE / n for n in ("structured.py", "identity.py", "projection.py", "postgres.py", "labels.yaml")]
    files.append(HERE.parent / "deploy/patient360/sql/fhir/00-roles-extensions.sql")
    return {"version": "structured-v1", "digests": {p.name: sha256(p) for p in files}}


def prepare(batch, registry, output):
    source = verify_batch(batch)
    baseline = read_json(DEFAULT_CONFIG)
    if source["contract"]["config"] != baseline:
        raise BatchError("source_namespace_not_approved")
    policy = policy_contract()
    projection_id = hashlib.sha256(canonical({"batch": source["batch_id"], "policy": policy,
                                              "registry": registry.identity})).hexdigest()
    destination = output / projection_id
    rows = {name: [] for name in postgres.TABLES}
    projector = Projector(registry, read_json(HERE / "labels.yaml"))
    try:
        with registry.db:
            for path in sorted((batch / "artifacts/source/fhir").glob("*.json")):
                bundle = read_json(path)
                relative = path.relative_to(batch).as_posix()
                part = projector.project(bundle, source["batch_id"], relative, sha256(path))
                for table in rows:
                    rows[table].extend(part[table])
            # Recheck immutable inputs after projection to catch concurrent edits.
            if verify_batch(batch) != source:
                raise BatchError("source_changed_during_preparation")
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise BatchError("unsupported_source_shape") from error
    for table, records in rows.items():
        key = "patient_key" if table == "patients" else "source_id"
        records.sort(key=lambda row: row[key])
        if len({row[key] for row in records}) != len(records):
            raise BatchError("duplicate_projected_identity")
    manifest = {"stage": "structured_prepared", "schema_version": 1,
                "namespace": NAMESPACE, "registry": registry.identity,
                "batch_id": source["batch_id"], "source_contract": source["contract"],
                "policy": policy, "counts": {t: len(r) for t, r in rows.items()},
                "skipped": dict(sorted(projector.skipped.items())), "published": False,
                "notes_sanitized": False, "projection_id": projection_id}
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.stat().st_mode & 0o077:
        raise BatchError("prepared_permissions_too_broad")
    if destination.exists():
        existing = read_json(destination / "manifest.json")
        if {k: v for k, v in existing.items() if k != "artifacts"} != manifest:
            raise BatchError("prepared_manifest_mismatch")
        if inventory(destination / "artifacts") != existing["artifacts"]:
            raise BatchError("prepared_artifact_corrupt")
        for table, records in rows.items():
            if (destination / "artifacts" / f"{table}.json").read_bytes() != canonical(records) + b"\n":
                raise BatchError("prepared_projection_mismatch")
        return rows, existing, destination
    attempt = Path(tempfile.mkdtemp(prefix=".structured-", dir=output))
    artifacts = attempt / "artifacts"
    artifacts.mkdir(mode=0o700)
    for table, records in rows.items():
        write_json(artifacts / f"{table}.json", records)
    manifest["artifacts"] = inventory(artifacts)
    write_json(attempt / "manifest.json", manifest)
    attempt.rename(destination)
    return rows, manifest, destination


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init-registry", "backup-registry", "prepare", "load"))
    parser.add_argument("batch", nargs="?", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--container", default="patient360-postgres")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Exercise PostgreSQL transaction then roll back")
    args = parser.parse_args(argv)
    registry = None
    try:
        if args.command == "init-registry":
            # Bootstrap is explicit and permitted only for an empty clinical DB.
            if postgres.query("SELECT count(*) FROM clinical.patients;", args.container) != "0":
                raise BatchError("existing_patients_restore_registry_required")
            registry = Registry.initialize(args.registry)
            print(json.dumps({"status": "registry_initialized", "namespace": NAMESPACE}))
            return 0
        registry = Registry(args.registry)
        with output_lock(args.registry.parent):
            if args.command == "backup-registry":
                if args.backup is None: raise BatchError("backup_path_required")
                registry.backup(args.backup)
                print(json.dumps({"status": "registry_backed_up"}))
                return 0
            if args.batch is None: raise BatchError("batch_path_required")
            rows, manifest, destination = prepare(args.batch.resolve(), registry, args.output)
            result = {"status": "structured_prepared", "prepared": str(destination),
                      "counts": manifest["counts"], "published": False}
            if args.command == "load":
                result.update(postgres.load(rows, manifest, args.container, args.dry_run))
                result["status"] = "structured_rolled_back" if args.dry_run else "structured_loaded"
                # Separate mutable receipt; prepared artifact hashes remain immutable.
                write_json(destination / "load-receipt.json", result)
            print(json.dumps(result, sort_keys=True))
        return 0
    except (BatchError, OSError, sqlite3.Error) as error:
        code = str(error) if isinstance(error, BatchError) else "structured_io_failure"
        print(json.dumps({"status": "failed", "error": code, "published": False}), file=sys.stderr)
        return 1
    finally:
        if registry is not None: registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
