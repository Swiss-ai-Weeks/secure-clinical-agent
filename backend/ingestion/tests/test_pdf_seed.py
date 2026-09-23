from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "ingestion"))

from pdf_seed import render_pdf, sanitized_demo_text  # noqa: E402


class PdfSeedTests(unittest.TestCase):
    def test_pdf_starts_with_header_and_drops_identifiers(self):
        text = sanitized_demo_text("p101-admission-2026-09-10")
        pdf = render_pdf("Discharge summary", text)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertNotIn(b"Elisabeth", pdf)
        self.assertNotIn(b"Keller", pdf)
        self.assertNotIn(b"+41", pdf)
        self.assertNotIn(b"MRN-4471902", pdf)
        self.assertIn(b"Discharge summary", pdf)


if __name__ == "__main__":
    unittest.main()
