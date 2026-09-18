"""Projection privacy, identity continuity, and transaction-boundary regressions."""

import base64
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from identity import Registry
from projection import Projector, LOINC, SNOMED, FHIR
import postgres
from worker import BatchError, read_json


def concept(code, system=LOINC):
    return {"coding": [{"system": system, "code": code, "display": "CANARY display"}],
            "text": "CANARY concept text", "extension": [{"valueString": "CANARY extension"}]}


def fixture():
    p = {"reference": "urn:uuid:p"}
    enc = {"reference": "urn:uuid:e"}
    rs = [
        {"resourceType": "Patient", "id": "p", "gender": "female", "birthDate": "1981-02-03",
         "name": [{"text": "CANARY name"}], "address": [{"text": "CANARY address"}]},
        {"resourceType": "Encounter", "id": "e", "subject": p, "status": "finished",
         "class": {"system": FHIR + "v3-ActCode", "code": "AMB", "display": "CANARY"},
         "type": [concept("185349003", SNOMED)],
         "period": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z"}},
        {"resourceType": "Condition", "id": "c", "subject": p, "encounter": enc,
         "code": concept("59621000", SNOMED)},
        {"resourceType": "Observation", "id": "o", "subject": p, "encounter": enc,
         "status": "final", "code": concept("85354-9"),
         "effectiveDateTime": "2026-01-01T00:01:00Z", "component": [
             {"code": concept("8480-6"), "valueQuantity": {"value": 143, "code": "mm[Hg]",
                 "unit": "CANARY unit", "system": "http://unitsofmeasure.org"}},
             {"code": concept("8462-4"), "valueQuantity": {"value": 89, "code": "mm[Hg]"}},
             {"code": concept("56799-0"), "valueString": "CANARY street address"}]},
    ]
    rs.append({"resourceType": "DocumentReference", "id": "d", "subject": p,
               "status": "current", "context": {"encounter": [enc]},
               "content": [{"attachment": {"contentType": "text/plain",
                   "data": base64.b64encode(b"CANARY raw note").decode()}}]})
    return {"resourceType": "Bundle", "type": "collection", "entry": [
        {"fullUrl": "urn:uuid:" + r["id"], "resource": r} for r in rs]}


class StructuredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "registry.sqlite"
        self.registry = Registry.initialize(self.path)
        self.addCleanup(lambda: self.registry.close())
        self.policy = read_json(Path(__file__).resolve().parents[1] / "labels.yaml")
        self.projector = Projector(self.registry, self.policy)

    def project(self, bundle=None, batch="batch"):
        with self.registry.db:
            return self.projector.project(bundle or fixture(), batch, "restricted/source", "digest")

    def test_numeric_components_links_and_no_identifier_or_dob_leakage(self):
        rows = self.project()
        text = json.dumps(rows)
        self.assertNotIn("CANARY", text)
        self.assertNotIn("1981-02-03", text)
        self.assertNotIn("56799-0", text)
        self.assertNotIn("Patient/p", text)
        patient = rows["patients"][0]
        self.assertRegex(patient["patient_key"], r"^p_[0-9a-f]{32}$")
        self.assertEqual(patient["resource"]["birthDate"], "1981")
        parent = next(r for r in rows["observations"] if r["parent_id"] is None)
        children = [r for r in rows["observations"] if r["parent_id"] is not None]
        self.assertEqual({r["value_num"] for r in children}, {143, 89})
        for row in children:
            self.assertEqual(row["unit"], "mm[Hg]")
            self.assertEqual(row["parent_id"], parent["id"])
            self.assertEqual(row["encounter_id"], rows["encounters"][0]["id"])
            self.assertEqual(row["patient_key"], patient["patient_key"])

    def test_identity_across_batches_restarts_backup_restore_and_updates(self):
        before = self.project()
        backup = self.path.with_name("backup.sqlite")
        self.registry.backup(backup)
        restored = Registry(backup)
        self.addCleanup(restored.close)
        projector = Projector(restored, self.policy)
        after = projector.project(fixture(), "seed", "restricted/source", "digest")
        self.assertEqual(before, after)
        changed = fixture()
        changed["entry"][3]["resource"]["component"][0]["valueQuantity"]["value"] = 144
        updates = self.project(changed, "revision")
        self.assertEqual(before["patients"], updates["patients"])
        self.assertEqual(before["observations"][0]["id"], updates["observations"][0]["id"])
        self.assertEqual(before["observations"][0]["cite_id"], updates["observations"][0]["cite_id"])
        self.assertEqual(updates["observations"][0]["value_num"], 144)
        with self.assertRaisesRegex(BatchError, "immutable_provenance"):
            self.project(changed)

    def test_missing_or_corrupt_registry_never_reinitializes(self):
        with self.assertRaisesRegex(BatchError, "restore_required"):
            Registry(self.path.with_name("absent"))
        broken = self.path.with_name("broken")
        broken.write_text("not sqlite")
        broken.chmod(0o600)
        with self.assertRaisesRegex(BatchError, "corrupt"):
            Registry(broken)
        with self.assertRaises(FileExistsError):
            Registry.initialize(self.path)

    def test_namespace_and_ownership_boundaries(self):
        self.project()
        with self.assertRaisesRegex(BatchError, "source_patient_changed"):
            self.registry.allocate("Observation/o", "Patient/other")
        self.registry.db.execute("UPDATE metadata SET value='other' WHERE key='namespace'")
        self.registry.db.commit()
        with self.assertRaisesRegex(BatchError, "contract_mismatch"):
            Registry(self.path)

    def test_invalid_references_rejected(self):
        for ref in ("Patient/p", "Encounter/missing", "https://untrusted/Encounter/e", "#e", "Encounter/e/_history/1"):
            with self.subTest(ref=ref):
                b = fixture()
                b["entry"][2]["resource"]["encounter"] = {"reference": ref}
                with self.assertRaises(BatchError): self.project(b)

    def test_cross_patient_encounter_rejected(self):
        b = fixture()
        b["entry"][1]["resource"]["subject"] = {"reference": "Patient/elsewhere"}
        with self.assertRaises(BatchError): self.project(b)

    def test_null_optional_and_missing_required(self):
        b = fixture()
        del b["entry"][0]["resource"]["gender"]
        del b["entry"][0]["resource"]["birthDate"]
        del b["entry"][2]["resource"]["code"]
        rows = self.project(b)
        self.assertIsNone(rows["patients"][0]["sex"])
        self.assertIsNone(rows["patients"][0]["birth_year"])
        self.assertIsNone(rows["conditions"][0]["code"])
        self.assertIsNone(rows["conditions"][0]["clinical_status"])
        for field in ("status", "code"):
            b = fixture()
            del b["entry"][3]["resource"][field]
            with self.assertRaises(BatchError): self.project(b, field)

    def test_unknown_code_rejected_instead_of_default_normal(self):
        b = fixture()
        b["entry"][2]["resource"]["code"] = concept("unreviewed", SNOMED)
        with self.assertRaisesRegex(BatchError, "unreviewed_clinical_code"): self.project(b)

    def test_duplicate_component_and_multiple_values_rejected(self):
        b = fixture()
        b["entry"][3]["resource"]["component"].append(copy.deepcopy(b["entry"][3]["resource"]["component"][0]))
        with self.assertRaisesRegex(BatchError, "ambiguous_component"): self.project(b)
        b = fixture()
        b["entry"][3]["resource"].update(valueInteger=0, valueBoolean=False)
        with self.assertRaisesRegex(BatchError, "multiple_observation_values"): self.project(b, "other")

    def test_coded_results_reasons_and_components_raise_labels(self):
        b = fixture()
        b["entry"][1]["resource"]["reasonCode"] = [concept("62479008", SNOMED)]
        b["entry"][3]["resource"]["component"].append({"code": concept("69453-9"),
            "valueCodeableConcept": concept("62479008", SNOMED)})
        rows = self.project(b)
        self.assertEqual(rows["encounters"][0]["confidentiality"], "V")
        parent = next(r for r in rows["observations"] if r["parent_id"] is None)
        self.assertEqual(parent["confidentiality"], "V")
        self.assertEqual(parent["sensitivity"], ["HIV"])
        child = next(r for r in rows["observations"] if r["code"] == "69453-9")
        self.assertEqual(child["confidentiality"], "V")
        self.assertEqual(child["value_code"], "62479008")

    def test_text_dictionary_and_zero_false_preserved(self):
        for field, value, column in (("valueInteger", 0, "value_num"), ("valueBoolean", False, "value_bool"),
                                     ("valueString", "elective", "value_text")):
            b = fixture()
            r = b["entry"][3]["resource"]
            r.pop("component")
            r.update(code=concept("X9999-1"), **{field: value})
            rows = self.project(b, field)
            self.assertEqual(rows["observations"][0][column], value)
        b["entry"][3]["resource"]["valueString"] = "CANARY narrative with identity"
        rows = self.project(b, "free-text")
        self.assertIsNone(rows["observations"][0]["value_text"])
        self.assertNotIn("CANARY", json.dumps(rows))

    def test_alternate_codings_safe_and_loinc_preferred(self):
        b = fixture()
        r = b["entry"][3]["resource"]
        r["code"]["coding"].insert(0, concept("271605009", SNOMED)["coding"][0])
        rows = self.project(b)
        parent = next(r for r in rows["observations"] if r["parent_id"] is None)
        self.assertEqual(parent["code_system"], LOINC)
        self.assertEqual(len(parent["resource"]["code"]["coding"]), 2)
        self.assertNotIn("CANARY", json.dumps(parent))

    def test_numeric_nonfinite_and_bad_units_rejected(self):
        for value in (float("nan"), float("inf"), True, "123"):
            b = fixture()
            b["entry"][3]["resource"]["component"][0]["valueQuantity"]["value"] = value
            with self.assertRaisesRegex(BatchError, "invalid_numeric"): self.project(b)
        b = fixture()
        b["entry"][3]["resource"]["component"][0]["valueQuantity"]["code"] = "CANARY"
        with self.assertRaisesRegex(BatchError, "unreviewed_unit"): self.project(b)

    def test_document_lineage_stays_restricted(self):
        rows = self.project()
        links = self.registry.db.execute("SELECT source, relation, target FROM resource_links").fetchall()
        self.assertEqual(links, [("DocumentReference/d", "encounter", "Encounter/e")])
        self.assertNotIn("DocumentReference/d", json.dumps(rows))

    def test_intervals_and_reference_ranges_reject_reversal(self):
        b = fixture()
        b["entry"][1]["resource"]["period"]["end"] = "2025-01-01T00:00:00Z"
        with self.assertRaisesRegex(BatchError, "reversed_clinical_interval"): self.project(b)
        b = fixture()
        b["entry"][3]["resource"]["referenceRange"] = [{"low": {"value": 2}, "high": {"value": 1}}]
        with self.assertRaisesRegex(BatchError, "reversed_reference_range"): self.project(b, "range")

    def test_no_raw_sql_error_in_diagnostics(self):
        class Failed:
            returncode = 1
            stdout = ""
            stderr = "CANARY row with source identity"
        with patch("postgres.subprocess.run", return_value=Failed()):
            with self.assertRaisesRegex(BatchError, "^postgres_transaction_rejected$"):
                postgres.query("SELECT 1")


if __name__ == "__main__": unittest.main()
