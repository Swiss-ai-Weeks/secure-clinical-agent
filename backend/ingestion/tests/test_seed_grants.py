import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seed_grants import plan  # noqa: E402


class SeedGrantsTests(unittest.TestCase):
    def test_no_bulk_on_remaining(self):
        body = plan(["p_syn_a", "p_syn_b", "p_syn_c"])
        self.assertEqual(body["bulk_remaining"], 0)
        objects = [w["object"] for w in body["writes"] if w.get("kind") == "synthea_demo"]
        self.assertEqual(objects, ["patient:p_syn_a", "patient:p_syn_b", "patient:p_syn_c"])
        self.assertTrue(all(w["user"] == "user:u_chen" for w in body["writes"] if w.get("kind") == "synthea_demo"))
        self.assertTrue(any(c["detail"]["seeded"] for c in body["consents"]))
        self.assertTrue(any(w["kind"] == "admission" for w in body["writes"]))

    def test_cli_json(self):
        from seed_grants import main

        self.assertEqual(main(["--dry-run"]), 0)
