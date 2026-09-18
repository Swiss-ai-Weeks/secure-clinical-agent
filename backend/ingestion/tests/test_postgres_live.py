"""Opt-in worker-role integration checks. Every test rolls its rows back.

RUN_STRUCTURED_POSTGRES_TESTS=1 python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py'
"""
import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch

import test_structured
import postgres
from worker import BatchError


@unittest.skipUnless(os.environ.get("RUN_STRUCTURED_POSTGRES_TESTS") == "1", "live PostgreSQL opt-in")
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_structured.StructuredTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.rows = self.fixture.project()
        self.manifest = {"batch_id": "integration-fixture", "policy": {}, "counts": {},
                         "source_contract": {}, "skipped": {}}

    def sql(self, rows):
        fake = "\n".join(json.dumps({"table": t, "changed": 0}) for t in postgres.TABLES)
        with patch("postgres.query", return_value=fake) as query:
            postgres.load(rows, self.manifest, dry_run=True)
        return query.call_args.args[0]

    def chain(self, *batches, extra=""):
        sections = []
        for i, rows in enumerate(batches):
            sql = self.sql(rows).removesuffix("ROLLBACK;")
            if i:
                sql = sql.removeprefix("BEGIN;")
                sections.append("DROP TABLE " + ",".join("stage_" + t for t in postgres.TABLES) + ";")
            sections.append(sql)
        return postgres.query("\n".join(sections) + extra + "\nROLLBACK;")

    def test_insert_then_identical_replay_changes_zero(self):
        output = self.chain(self.rows, self.rows)
        changes = [json.loads(s) for s in output.splitlines() if s.startswith("{")]
        self.assertEqual([x["changed"] for x in changes[:4]], [1, 1, 1, 3])
        self.assertEqual([x["changed"] for x in changes[4:]], [0, 0, 0, 0])

    def test_changed_measurement_preserves_identity_and_null_clears(self):
        changed = copy.deepcopy(self.rows)
        child = changed["observations"][0]
        child["value_num"] = 144
        child["resource"]["valueQuantity"]["value"] = 144
        changed["conditions"][0]["encounter_id"] = None
        output = self.chain(self.rows, changed)
        changes = [json.loads(s) for s in output.splitlines() if s.startswith("{")]
        self.assertEqual([x["changed"] for x in changes[4:]], [0, 0, 1, 2])

    def test_removed_component_aborts_entire_import(self):
        changed = copy.deepcopy(self.rows)
        changed["observations"].pop(0)
        with self.assertRaises(BatchError): self.chain(self.rows, changed)
        self.assertEqual(postgres.query("SELECT count(*) FROM clinical.patients WHERE patient_key=" +
                         postgres.literal(self.rows["patients"][0]["patient_key"]) + ";"), "0")

    def test_registry_mismatch_aborts(self):
        changed = copy.deepcopy(self.rows)
        changed["observations"][0]["cite_id"] = "obs_other"
        with self.assertRaises(BatchError): self.chain(self.rows, changed)

    def test_large_replay_finishes_within_statement_budget(self):
        # Same importer path as the real 70k-row replay. A missing staging index
        # makes the source-removal check repeatedly scan this entire table.
        rows = copy.deepcopy(self.rows)
        parent = next(r for r in rows["observations"] if r["parent_id"] is None)
        rows["observations"] = [dict(parent, id=str(uuid.uuid4()),
            cite_id=f"obs_replay_{i}", source_id=f"Observation/replay_{i}") for i in range(12000)]
        first = self.sql(rows).removesuffix("ROLLBACK;")
        second = self.sql(rows).removeprefix("BEGIN;")
        second = second.replace("statement_timeout='120s'", "statement_timeout='2s'")
        sql = first + "DROP TABLE " + ",".join("stage_" + t for t in postgres.TABLES) + ";" + second
        output = postgres.query(sql)
        changes = [json.loads(s) for s in output.splitlines() if s.startswith("{")]
        self.assertEqual([x["changed"] for x in changes[4:]], [0, 0, 0, 0])

    def test_cross_patient_fk_and_worker_delete_denied(self):
        changed = copy.deepcopy(self.rows)
        changed["patients"].append(dict(changed["patients"][0], patient_key="p_integrationother"))
        changed["observations"][0]["patient_key"] = "p_integrationother"
        with self.assertRaises(BatchError): self.chain(changed)
        with self.assertRaises(BatchError):
            postgres.query("BEGIN; DELETE FROM clinical.patients WHERE false; ROLLBACK;")
