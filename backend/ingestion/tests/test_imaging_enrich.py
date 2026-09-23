from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imaging_enrich import _maybe_json, medgemma_describe, persist_vista_overlay, vista_segment


class EnrichClientTests(unittest.TestCase):
    def test_medgemma_payload_includes_image(self):
        captured = {}

        def fake_json(url, payload=None, timeout=0):
            captured["url"] = url
            captured["payload"] = payload
            return 200, {"choices": [{"message": {"content": "Synthetic chest geometry."}}]}, b"{}"

        with patch("imaging_enrich._json_request", side_effect=fake_json):
            text = medgemma_describe("http://medgemma.test", "google/medgemma-1.5-4b-it", b"png")
        self.assertEqual(text, "Synthetic chest geometry.")
        self.assertTrue(captured["url"].endswith("/v1/chat/completions"))
        content = captured["payload"]["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_vista_persist_keeps_class_names(self):
        captured = {}

        class FakeOverlay:
            seg_bytes = b"SEG"
            report_text = "VISTA-3D overlay on CT: heart. Toggle the segmentation in the study viewer."

        def fake_build(mask, source, *, classes, study_key):
            captured["mask"] = mask
            captured["source"] = source
            captured["classes"] = classes
            captured["study_key"] = study_key
            return FakeOverlay()

        class FakeOrthanc:
            def store(self, payload):
                captured["stored"] = payload
                return {"ParentStudy": "s1"}

        with (
            patch("imaging_enrich._orthanc_ct_files", return_value=[b"CT"]),
            patch("imaging_enrich._delete_vista_seg"),
            patch("patient360.vista_overlay.build_overlay", fake_build),
        ):
            overlay = persist_vista_overlay(
                FakeOrthanc(), "orthanc-1", b"mask-bytes", classes=("heart",), study_key="p102-ct-2026-07-01"
            )
        self.assertEqual(overlay.report_text, FakeOverlay.report_text)
        self.assertEqual(captured["stored"], b"SEG")
        self.assertEqual(captured["classes"], ("heart",))
        self.assertNotIn("320 bytes", overlay.report_text)

    def test_vista_payload_uses_mounted_path(self):
        captured = {}

        def fake_json(url, payload=None, timeout=0):
            captured["url"] = url
            captured["payload"] = payload
            return 200, None, b"PK\x03\x04zip"

        with patch("imaging_enrich._json_request", side_effect=fake_json):
            raw = vista_segment("http://vista.test", "/data/patient360/p102-ct-2026-07-01", ("heart",))
        self.assertEqual(raw, b"PK\x03\x04zip")
        self.assertTrue(captured["url"].endswith("/v1/vista3d/inference"))
        self.assertEqual(captured["payload"]["image"], "/data/patient360/p102-ct-2026-07-01")
        self.assertEqual(captured["payload"]["prompts"]["classes"], ["heart"])

    def test_maybe_json_ignores_zip_bytes(self):
        self.assertIsNone(_maybe_json(b"PK\x03\x04not-json"))

    def test_medgemma_errors_on_http_failure(self):
        with patch("imaging_enrich._json_request", return_value=(503, {"error": "down"}, b"")):
            with self.assertRaises(RuntimeError):
                medgemma_describe("http://medgemma.test", "m", b"png")


if __name__ == "__main__":
    unittest.main()
