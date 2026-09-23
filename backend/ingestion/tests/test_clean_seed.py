import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from clean_seed import statements  # noqa: E402
from patient360.clinical_view import CLINICAL_CONDITION_PATTERN  # noqa: E402


class CleanSeedTests(unittest.TestCase):
    def test_deletes_surveys_and_synthea_social_conditions_only(self):
        sql = " ".join(statements())
        self.assertIn("category IN ('survey', 'social-history')", sql)
        self.assertIn("category NOT IN ('laboratory', 'vital-signs')", sql)
        self.assertIn("length(patient_key) > 8", sql)
        self.assertIn(CLINICAL_CONDITION_PATTERN, sql)
        self.assertIn("!~*", sql)
        self.assertNotIn("p_101", sql)
