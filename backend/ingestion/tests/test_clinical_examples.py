import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "ingestion"))

from clinical_examples import EVIDENCE, REGISTRY, load_examples  # noqa: E402
from notes import prepare_note  # noqa: E402
from patient360.deid import hints_from_mapping  # noqa: E402
from vector_test_support import TokenizerTestCase  # noqa: E402


@unittest.skipUnless(EVIDENCE.is_file() and REGISTRY.is_file(), "restricted source evidence not present")
class ClinicalExampleTests(TokenizerTestCase):
    def test_three_keys_and_sanitized_notes(self):
        rows = load_examples()
        self.assertEqual(len(rows), 3)
        aliases = {row["example"] for row in rows}
        self.assertEqual(
            aliases,
            {"diabetes-self-management", "hypertension-education", "historical-pneumonia"},
        )
        keys = [row["patient_key"] for row in rows]
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(key.startswith("p_") for key in keys))
        for row in rows:
            hints = hints_from_mapping(
                names=tuple(row["names"]),
                dob_strings=tuple(row["dob_strings"]),
                mrns=tuple(row["mrns"]),
                phones=tuple(row["phones"]),
                source_ids=tuple(row["source_ids"]),
            )
            prepared = prepare_note(row["note_id"], row["text"], hints)
            self.assertTrue(prepared["ok"], prepared)
            lowered = prepared["text"].lower()
            for name in row["names"]:
                self.assertNotIn(name.lower(), lowered)
            for phrase in (
                "type 2 diabetes",
                "self-management",
                "essential hypertension",
                "lifestyle education",
                "pneumonia",
                "hypoxemia",
            ):
                if phrase in row["text"].lower():
                    self.assertIn(phrase, lowered)


if __name__ == "__main__":
    unittest.main()
