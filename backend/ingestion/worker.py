#!/usr/bin/env python3
"""Repeatable, restricted Synthea source batches. No store publication occurs here."""

from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).parent / "config" / "synthea.json"
CONTRACT_VERSION = 1


class BatchError(Exception):
    """A safe diagnostic code, never raw source data or command output."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as error:
        raise BatchError("invalid_json_artifact") from error


def write_json(path, value):
    path.write_bytes(canonical(value) + b"\n")
    path.chmod(0o600)


def load_config(path, profile):
    config = read_json(path)
    required = {
        "schema_version", "synthea_version", "synthea_commit", "jar_url", "jar_sha256",
        "java_image", "platform", "profiles", "population_seed", "clinician_seed",
        "reference_date", "end_date", "state", "years_of_history", "timeout_seconds",
    }
    if not isinstance(config, dict) or set(config) != required or config["schema_version"] != 1:
        raise BatchError("invalid_source_config")
    if not re.fullmatch(r"[0-9a-f]{64}", str(config["jar_sha256"])):
        raise BatchError("jar_digest_required")
    if not re.fullmatch(r"[0-9a-f]{40}", str(config["synthea_commit"])):
        raise BatchError("source_revision_required")
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", str(config["java_image"])):
        raise BatchError("runtime_digest_required")
    expected_url = ("https://github.com/synthetichealth/synthea/releases/download/v"
                    + str(config["synthea_version"]) + "/synthea-with-dependencies.jar")
    if config["jar_url"] != expected_url:
        raise BatchError("unrecognized_jar_url")
    if config["platform"] != "linux/amd64":
        raise BatchError("unsupported_runtime_platform")
    if not isinstance(config["profiles"], dict) or profile not in config["profiles"]:
        raise BatchError("unknown_profile")
    for name in ("population_seed", "clinician_seed", "years_of_history", "timeout_seconds"):
        if type(config[name]) is not int or config[name] < 0:
            raise BatchError("invalid_numeric_config")
    if not 1 <= config["timeout_seconds"] <= 86400:
        raise BatchError("invalid_timeout")
    population = config["profiles"][profile]
    if type(population) is not int or not 1 <= population <= 10000:
        raise BatchError("invalid_population")
    try:
        for name in ("reference_date", "end_date"):
            if not isinstance(config[name], str) or not re.fullmatch(r"\d{8}", config[name]):
                raise ValueError()
            datetime.strptime(config[name], "%Y%m%d")
        if config["reference_date"] > config["end_date"]:
            raise ValueError()
    except ValueError as error:
        raise BatchError("invalid_fixed_dates") from error
    if not isinstance(config["state"], str) or not re.fullmatch(r"[A-Za-z ]+", config["state"]):
        raise BatchError("invalid_state")
    return config


def source_contract(config, profile):
    """All generation inputs, including the adapter implementation revision."""
    return {
        "worker_contract_version": CONTRACT_VERSION,
        "worker_sha256": sha256(Path(__file__)),
        "config": config,
        "profile": profile,
        "population": config["profiles"][profile],
    }


def batch_id(contract):
    return hashlib.sha256(canonical(contract)).hexdigest()


def ensure_jar(config, cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (config["jar_sha256"] + ".jar")
    if path.exists():
        if sha256(path) != config["jar_sha256"]:
            raise BatchError("cached_jar_digest_mismatch")
        return path
    descriptor, temporary = tempfile.mkstemp(prefix="download-", dir=cache)
    try:
        with os.fdopen(descriptor, "wb") as output:
            with urllib.request.urlopen(config["jar_url"], timeout=60) as response:
                while data := response.read(1024 * 1024):
                    output.write(data)
        candidate = Path(temporary)
        if sha256(candidate) != config["jar_sha256"]:
            raise BatchError("downloaded_jar_digest_mismatch")
        candidate.replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def generation_command(config, population, jar, output, name):
    # The container gets no network, credentials, host home, or access to stores.
    properties = {
        "exporter.baseDirectory": "/output",
        "exporter.fhir.export": "true",
        "exporter.fhir.use_us_core_ig": "true",
        "exporter.fhir.us_core_version": "6.1.0",
        "exporter.fhir.transaction_bundle": "false",
        "exporter.fhir.bulk_data": "false",
        "exporter.hospital.fhir.export": "false",
        "exporter.practitioner.fhir.export": "false",
        "exporter.metadata.export": "false",
        "exporter.use_uuid_filenames": "true",
        "exporter.split_records": "false",
        "exporter.years_of_history": str(config["years_of_history"]),
        "generate.thread_pool_size": "1",
        "generate.log_patients.detail": "none",
    }
    return [
        "docker", "run", "--rm", "--name", name,
        "--platform", config["platform"], "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", f"{os.getuid()}:{os.getgid()}", "--memory", "4g", "--cpus", "2",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m", "--env", "TZ=UTC",
        "--mount", f"type=bind,src={jar.resolve()},dst=/synthea.jar,readonly",
        "--mount", f"type=bind,src={output.resolve()},dst=/output",
        config["java_image"], "java", "-Xmx3g", "-Duser.timezone=UTC",
        "-Duser.language=en", "-Duser.country=US", "-jar", "/synthea.jar",
        "-p", str(population), "-s", str(config["population_seed"]),
        "-cs", str(config["clinician_seed"]), "-r", config["reference_date"],
        "-e", config["end_date"], "-o", "false",
        *[f"--{key}={value}" for key, value in sorted(properties.items())], config["state"],
    ]


def run_generator(config, population, jar, output, log):
    name = "patient360-synthea-" + uuid.uuid4().hex
    with log.open("wb") as stream:
        try:
            result = subprocess.run(
                generation_command(config, population, jar, output, name),
                stdout=stream, stderr=subprocess.STDOUT, timeout=config["timeout_seconds"],
                check=False,
            )
            if result.returncode:
                raise BatchError("synthea_process_failed")
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            # Killing the Docker client alone can leave the generation container alive.
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30, check=False)
            code = "synthea_timeout" if isinstance(error, subprocess.TimeoutExpired) else "synthea_interrupted"
            raise BatchError(code) from error


def extract_bundle(bundle):
    """Validate the supported Synthea boundary, returning linked *raw* notes.

    This checks structure and patient/encounter linkage, not full FHIR conformance.
    Never infer a patient by splitting an arbitrary absolute reference URL.
    """
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise BatchError("expected_fhir_bundle")
    if bundle.get("type") not in ("collection", "transaction"):
        raise BatchError("unsupported_bundle_type")
    entries = bundle.get("entry")
    if not isinstance(entries, list) or not entries:
        raise BatchError("empty_bundle")
    resources, references = {}, {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
            raise BatchError("invalid_bundle_entry")
        resource = entry["resource"]
        kind, identifier = resource.get("resourceType"), resource.get("id")
        if not isinstance(kind, str) or not isinstance(identifier, str) or not identifier:
            raise BatchError("missing_resource_identity")
        key = f"{kind}/{identifier}"
        if key in resources:
            raise BatchError("duplicate_resource_identity")
        resources[key] = resource
        for reference in {key, entry.get("fullUrl", key)}:
            if not isinstance(reference, str) or not reference:
                raise BatchError("invalid_reference")
            if reference in references and references[reference] != key:
                raise BatchError("ambiguous_reference")
            references[reference] = key
    patients = [key for key in resources if key.startswith("Patient/")]
    if len(patients) != 1:
        raise BatchError("expected_one_patient_per_bundle")
    patient = patients[0]

    def resolve(reference):
        if not isinstance(reference, dict) or reference.get("reference") not in references:
            raise BatchError("unresolved_reference")
        return references[reference["reference"]]

    notes = []
    for key, resource in sorted(resources.items()):
        kind = resource["resourceType"]
        if kind in ("Condition", "Observation", "Encounter", "DocumentReference"):
            if resolve(resource.get("subject")) != patient:
                raise BatchError("cross_patient_reference")
        if kind != "DocumentReference":
            continue
        context = resource.get("context", {})
        if not isinstance(context, dict):
            raise BatchError("invalid_note_context")
        encounters = context.get("encounter", [])
        if not isinstance(encounters, list) or not encounters:
            raise BatchError("missing_note_encounter")
        encounter_keys = sorted({resolve(value) for value in encounters})
        if any(not value.startswith("Encounter/") for value in encounter_keys):
            raise BatchError("invalid_note_encounter")
        contents = resource.get("content", [])
        if not isinstance(contents, list) or len(contents) != 1:
            raise BatchError("unsupported_note_content")
        if not isinstance(contents[0], dict) or not isinstance(contents[0].get("attachment"), dict):
            raise BatchError("unsupported_note_content")
        attachment = contents[0]["attachment"]
        media = attachment.get("contentType")
        if not isinstance(media, str) or media.split(";")[0].strip() != "text/plain":
            raise BatchError("unsupported_note_media")
        try:
            text = base64.b64decode(attachment["data"], validate=True).decode("utf-8")
        except (KeyError, ValueError, TypeError, binascii.Error, UnicodeError) as error:
            raise BatchError("invalid_note_encoding") from error
        if not text.strip():
            raise BatchError("empty_note")
        notes.append({
            "source_patient_id": patient, "source_document_id": key,
            "source_encounter_ids": encounter_keys, "date": resource.get("date"),
            "text": text, "synthetic": True, "sanitized": False,
            "generator": "synthea-clinical-note-template",
        })
    if not notes:
        raise BatchError("missing_clinical_notes")
    return patient, Counter(resource["resourceType"] for resource in resources.values()), notes


def inspect_source(output, expected_population):
    files = sorted((output / "fhir").glob("*.json"))
    if not files:
        raise BatchError("missing_fhir_output")
    patients, counts, notes = set(), Counter(), []
    for path in files:
        if path.is_symlink() or path.stat().st_size > 128 * 1024 * 1024:
            raise BatchError("unsafe_source_file")
        patient, resources, extracted = extract_bundle(read_json(path))
        if patient in patients:
            raise BatchError("duplicate_patient")
        patients.add(patient)
        counts.update(resources)
        bundle_digest = sha256(path)
        for note in extracted:
            note["source_bundle"] = path.relative_to(output).as_posix()
            note["source_bundle_sha256"] = bundle_digest
        notes.extend(extracted)
    if len(patients) != expected_population:
        raise BatchError("patient_count_mismatch")
    notes.sort(key=lambda note: (note["source_patient_id"], note["source_document_id"]))
    return {"patients": len(patients), "notes": len(notes), "resources": dict(sorted(counts.items()))}, notes


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise BatchError("symlink_artifact")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = {
                "sha256": sha256(path), "bytes": path.stat().st_size,
            }
    return result


def verify_batch(directory, expected_contract=None):
    manifest = read_json(directory / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("status") != "source_ready":
        raise BatchError("batch_not_source_ready")
    if (manifest.get("schema_version") != 1 or manifest.get("synthetic") is not True
            or manifest.get("sanitized") is not False or manifest.get("published") is not False):
        raise BatchError("invalid_source_stage_claim")
    contract = manifest.get("contract")
    if not isinstance(contract, dict) or batch_id(contract) != manifest.get("batch_id"):
        raise BatchError("batch_identity_mismatch")
    if expected_contract is not None and contract != expected_contract:
        raise BatchError("batch_contract_mismatch")
    if inventory(directory / "artifacts") != manifest.get("artifacts"):
        raise BatchError("artifact_integrity_failure")
    counts, notes = inspect_source(directory / "artifacts" / "source", contract["population"])
    if counts != manifest.get("counts"):
        raise BatchError("manifest_count_mismatch")
    expected_notes = b"".join(canonical(note) + b"\n" for note in notes)
    if (directory / "artifacts" / "raw-notes.jsonl").read_bytes() != expected_notes:
        raise BatchError("note_lineage_mismatch")
    return manifest


@contextmanager
def output_lock(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise BatchError("worker_already_running") from error
        yield


def run_batch(config, profile, root, cache):
    contract = source_contract(config, profile)
    identity = batch_id(contract)
    final = root / identity
    with output_lock(root):
        if final.exists():
            return verify_batch(final, contract), final, True
        jar = ensure_jar(config, cache)
        attempt = Path(tempfile.mkdtemp(prefix=f".attempt-{identity[:12]}-", dir=root))
        artifacts = attempt / "artifacts"
        output = artifacts / "source"
        output.mkdir(parents=True, mode=0o700)
        try:
            run_generator(config, contract["population"], jar, output, attempt / "generator.log")
            counts, notes = inspect_source(output, contract["population"])
            with (artifacts / "raw-notes.jsonl").open("wb") as stream:
                for note in notes:
                    stream.write(canonical(note) + b"\n")
            manifest = {
                "schema_version": 1, "status": "source_ready", "batch_id": identity,
                "contract": contract, "counts": counts, "artifacts": inventory(artifacts),
                "synthetic": True, "sanitized": False, "published": False,
            }
            write_json(attempt / "manifest.json", manifest)
            verify_batch(attempt, contract)
            attempt.rename(final)
            return manifest, final, False
        except Exception as error:
            code = str(error) if isinstance(error, BatchError) else "source_stage_failed"
            write_json(attempt / "failure.json", {"status": "failed", "code": code})
            raise BatchError(code) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Generate or verify/reuse a restricted source batch")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--profile", choices=("smoke", "seed"), default="smoke")
    run.add_argument("--output", type=Path, default=ROOT / ".data" / "ingestion")
    run.add_argument("--cache", type=Path, default=ROOT / ".cache" / "synthea")
    verify = sub.add_parser("verify", help="Verify all source hashes, counts, and note lineage")
    verify.add_argument("batch", type=Path)
    compare = sub.add_parser("compare", help="Check independently generated batches for exact equality")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "run":
            config = load_config(args.config, args.profile)
            manifest, path, reused = run_batch(config, args.profile, args.output.resolve(), args.cache.resolve())
            result = {"batch": str(path), "reused": reused}
        elif args.command == "verify":
            manifest = verify_batch(args.batch)
            result = {"verified": True}
        else:
            manifest = verify_batch(args.first)
            other = verify_batch(args.second)
            if manifest != other:
                raise BatchError("independent_runs_differ")
            result = {"independent_runs_equal": True}
        result.update(status=manifest["status"], batch_id=manifest["batch_id"], counts=manifest["counts"])
        print(json.dumps(result, sort_keys=True))
        return 0
    except (BatchError, OSError, KeyError, TypeError, ValueError) as error:
        code = str(error) if isinstance(error, BatchError) else "worker_io_or_contract_error"
        print(json.dumps({"status": "failed", "code": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
