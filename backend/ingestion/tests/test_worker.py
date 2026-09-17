"""Public CLI tests; Docker is replaced at the external process boundary."""

import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


INGESTION = Path(__file__).resolve().parents[1]
WORKER = INGESTION / "worker.py"


def bundle():
    def entry(kind, identifier, **fields):
        return {"fullUrl": f"urn:uuid:{identifier}",
                "resource": {"resourceType": kind, "id": identifier, **fields}}

    patient = {"reference": "urn:uuid:patient-a"}
    return {
        "resourceType": "Bundle", "type": "collection",
        "entry": [
            entry("Patient", "patient-a", name=[{"text": "Synthetic Canary"}]),
            entry("Encounter", "encounter-a", subject=patient),
            entry("Observation", "observation-a", subject=patient,
                  valueQuantity={"value": 120, "unit": "mmHg"}),
            entry("DocumentReference", "document-a", subject=patient, status="superseded",
                  date="2026-01-01T00:00:00Z",
                  context={"encounter": [{"reference": "urn:uuid:encounter-a"}]},
                  content=[{"attachment": {
                      "contentType": "text/plain; charset=utf-8",
                      "data": base64.b64encode(b"Synthetic Canary: BP 120 mmHg.").decode(),
                  }}]),
            # The same upstream note also has a DiagnosticReport representation.
            entry("DiagnosticReport", "report-a", subject=patient,
                  presentedForm=[{"data": base64.b64encode(b"Duplicate note.").decode()}]),
        ],
    }


class SourceWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "batches"
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.config = json.loads((INGESTION / "config/synthea.json").read_text())
        self.config["profiles"] = {"smoke": 1, "seed": 2}
        jar = b"synthetic test artifact, never executed as Java"
        self.config["jar_sha256"] = hashlib.sha256(jar).hexdigest()
        (self.cache / (self.config["jar_sha256"] + ".jar")).write_bytes(jar)
        self.config_path = self.root / "config.json"
        self.save_config()
        self.fixture_path = self.root / "bundle.json"
        self.save_bundle(bundle())
        self.counter = self.root / "docker-invocations"
        docker = self.root / "docker"
        docker.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, sys
counter = pathlib.Path(os.environ["TEST_COUNTER"])
counter.write_text(counter.read_text() + "run\\n" if counter.exists() else "run\\n")
if os.environ.get("TEST_DOCKER_FAILURE"):
    print("synthetic-sensitive-output-must-not-escape")
    sys.exit(42)
mount = next(arg for arg in sys.argv if arg.startswith("type=bind,src=") and arg.endswith("dst=/output"))
destination = pathlib.Path(mount.split("src=", 1)[1].split(",dst=", 1)[0]) / "fhir"
destination.mkdir()
destination.joinpath("patient-a.json").write_bytes(pathlib.Path(os.environ["TEST_FIXTURE"]).read_bytes())
''')
        docker.chmod(0o700)
        self.environment = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ["PATH"],
                                TEST_FIXTURE=str(self.fixture_path), TEST_COUNTER=str(self.counter))

    def save_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def save_bundle(self, value):
        self.fixture_path.write_text(json.dumps(value))

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(WORKER), *map(str, args)],
                                env=self.environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def run_worker(self, expected=0, output=None):
        return self.cli("run", "--config", self.config_path, "--output", output or self.output,
                        "--cache", self.cache, expected=expected)

    def test_source_batch_has_counts_and_exact_linked_historical_note_once(self):
        result = self.run_worker()
        self.assertEqual(result["counts"], {
            "patients": 1, "notes": 1,
            "resources": {"Patient": 1, "Encounter": 1, "Observation": 1,
                          "DocumentReference": 1, "DiagnosticReport": 1},
        })
        path = Path(result["batch"])
        note = json.loads((path / "artifacts/raw-notes.jsonl").read_text())
        self.assertEqual(note["text"], "Synthetic Canary: BP 120 mmHg.")
        self.assertEqual(note["source_patient_id"], "Patient/patient-a")
        self.assertEqual(note["source_encounter_ids"], ["Encounter/encounter-a"])
        self.assertEqual(note["source_document_id"], "DocumentReference/document-a")
        self.assertFalse(note["sanitized"])
        manifest = json.loads((path / "manifest.json").read_text())
        self.assertFalse(manifest["published"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertTrue(self.cli("verify", path)["verified"])

    def test_rerun_verifies_and_reuses_without_invoking_generator(self):
        first, second = self.run_worker(), self.run_worker()
        self.assertEqual(first["batch_id"], second["batch_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(self.counter.read_text().splitlines(), ["run"])

    def test_independent_runs_have_equal_artifact_manifests(self):
        first = self.run_worker()
        second = self.run_worker(output=self.root / "second")
        self.assertTrue(self.cli("compare", first["batch"], second["batch"])["independent_runs_equal"])
        self.assertEqual(len(self.counter.read_text().splitlines()), 2)

    def test_source_change_creates_different_batch_identity(self):
        first = self.run_worker()
        self.config["population_seed"] += 1
        self.save_config()
        second = self.run_worker()
        self.assertNotEqual(first["batch_id"], second["batch_id"])

    def test_corrupt_completed_artifact_is_rejected_without_regeneration(self):
        result = self.run_worker()
        (Path(result["batch"]) / "artifacts/raw-notes.jsonl").write_text("corrupt")
        self.assertEqual(self.run_worker(expected=1)["code"], "artifact_integrity_failure")
        self.assertEqual(len(self.counter.read_text().splitlines()), 1)

    def test_raw_source_cannot_claim_sanitized_or_published_status(self):
        result = self.run_worker()
        path = Path(result["batch"]) / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["sanitized"] = True
        path.write_text(json.dumps(manifest))
        self.assertEqual(self.cli("verify", result["batch"], expected=1)["code"],
                         "invalid_source_stage_claim")

    def test_a_concurrent_worker_cannot_start_a_second_generation(self):
        self.output.mkdir()
        with (self.output / ".worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.run_worker(expected=1)["code"], "worker_already_running")
        self.assertFalse(self.counter.exists())

    def test_failed_process_keeps_restricted_attempt_and_can_retry(self):
        self.environment["TEST_DOCKER_FAILURE"] = "1"
        self.assertEqual(self.run_worker(expected=1)["code"], "synthea_process_failed")
        self.assertEqual(list(self.output.glob("*/manifest.json")), [])
        failures = list(self.output.glob(".attempt-*/failure.json"))
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].parent.stat().st_mode & 0o777, 0o700)
        del self.environment["TEST_DOCKER_FAILURE"]
        self.assertFalse(self.run_worker()["reused"])

    def test_wrong_patient_count_cannot_become_source_ready(self):
        self.config["profiles"]["smoke"] = 2
        self.save_config()
        self.assertEqual(self.run_worker(expected=1)["code"], "patient_count_mismatch")
        self.assertEqual(list(self.output.glob("*/manifest.json")), [])

    def test_bad_cached_artifact_digest_is_rejected_before_execution(self):
        next(self.cache.glob("*.jar")).write_bytes(b"changed")
        self.assertEqual(self.run_worker(expected=1)["code"], "cached_jar_digest_mismatch")
        self.assertFalse(self.counter.exists())

    def test_mutable_java_tag_is_rejected(self):
        self.config["java_image"] = "eclipse-temurin:latest"
        self.save_config()
        self.assertEqual(self.run_worker(expected=1)["code"], "runtime_digest_required")

    def test_missing_or_invalid_fixed_date_is_rejected(self):
        for value in ("20260230", "202691", None):
            with self.subTest(value=value):
                self.config["end_date"] = value
                self.save_config()
                self.assertEqual(self.run_worker(expected=1)["code"], "invalid_fixed_dates")

    def test_unknown_subject_reference_is_rejected(self):
        source = bundle()
        source["entry"][3]["resource"]["subject"] = {"reference": "Patient/not-in-this-bundle"}
        self.save_bundle(source)
        self.assertEqual(self.run_worker(expected=1)["code"], "unresolved_reference")

    def test_note_cannot_link_to_a_non_encounter_resource(self):
        source = bundle()
        source["entry"][3]["resource"]["context"]["encounter"] = [{"reference": "urn:uuid:patient-a"}]
        self.save_bundle(source)
        self.assertEqual(self.run_worker(expected=1)["code"], "invalid_note_encounter")

    def test_ambiguous_full_url_is_rejected(self):
        source = bundle()
        source["entry"][1]["fullUrl"] = "urn:uuid:patient-a"
        self.save_bundle(source)
        self.assertEqual(self.run_worker(expected=1)["code"], "ambiguous_reference")

    def test_duplicate_resource_identity_is_rejected(self):
        source = bundle()
        source["entry"].append(copy.deepcopy(source["entry"][0]))
        self.save_bundle(source)
        self.assertEqual(self.run_worker(expected=1)["code"], "duplicate_resource_identity")

    def test_missing_document_reference_is_not_filled_from_diagnostic_report(self):
        source = bundle()
        del source["entry"][3]
        self.save_bundle(source)
        self.assertEqual(self.run_worker(expected=1)["code"], "missing_clinical_notes")

    def test_invalid_attachment_is_rejected(self):
        for data, media, code in [
            ("not base64!", "text/plain", "invalid_note_encoding"),
            ("", "text/plain", "empty_note"),
            ("YQ==", "application/pdf", "unsupported_note_media"),
        ]:
            with self.subTest(code=code):
                source = bundle()
                source["entry"][3]["resource"]["content"][0]["attachment"] = {
                    "data": data, "contentType": media,
                }
                self.save_bundle(source)
                self.assertEqual(self.run_worker(expected=1)["code"], code)


if __name__ == "__main__":
    unittest.main()
