from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imaging_catalog import STUDIES, dicom_uid, study_by_key


class CatalogTests(unittest.TestCase):
    def test_three_demo_patients(self):
        keys = [s.patient_key for s in STUDIES]
        self.assertEqual(
            keys,
            ["p_101", "p_102", "p_102", "p_103", "p_485ba8c8597d4c5cb0fbda55317119a3"],
        )
        for study in STUDIES:
            self.assertNotIn("Synthetic", study.description)
            self.assertTrue(study.report_ref.endswith(".pdf"))
            self.assertTrue(study.source_file)

    def test_uids_are_numeric_and_stable(self):
        first = dicom_uid("study", "p101-cxr-2026-09-11")
        self.assertTrue(first.startswith("2.25."))
        self.assertTrue(first[5:].isdigit())
        self.assertEqual(first, dicom_uid("study", "p101-cxr-2026-09-11"))
        self.assertNotEqual(first, dicom_uid("study", "p102-ct-2026-07-01"))

    def test_headers_use_opaque_patient_key_only(self):
        try:
            from dicom_seed import render_instance
        except ImportError:
            self.skipTest("pydicom is not installed")
        study = study_by_key("p101-cxr-2026-09-11")
        try:
            ds = render_instance(study, 0)
        except ModuleNotFoundError:
            self.skipTest("pydicom is not installed")
        self.assertEqual(str(ds.PatientID), "p_101")
        self.assertEqual(str(ds.PatientName), "p101")
        blob = " ".join(str(v) for v in ds.values())
        self.assertNotIn("Keller", blob)
        self.assertNotIn("Elisabeth", blob)

    def test_local_series_writes_expected_count(self):
        try:
            from dicom_seed import write_local_series
        except ImportError:
            self.skipTest("pydicom is not installed")
        study = study_by_key("p102-ct-2026-07-01")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                folder = write_local_series(study, Path(tmp))
                files = sorted(folder.glob("*.dcm"))
                self.assertEqual(len(files), 16)
                raw = files[0].read_bytes()
        except ModuleNotFoundError:
            self.skipTest("pydicom is not installed")
        self.assertEqual(raw[128:132], b"DICM")

    def test_retag_clears_planted_name(self):
        try:
            from pydicom.dataset import Dataset

            from dicom_seed import retag_instance
        except ImportError:
            self.skipTest("pydicom is not installed")
        raw = Dataset()
        raw.PatientName = "Elisabeth Keller"
        raw.PatientID = "MRN-4471902"
        raw.PatientBirthDate = "19610417"
        raw.PatientSex = "F"
        raw.PatientTelephoneNumbers = "+41 44 555 01 17"
        raw.SOPClassUID = "1.2.840.10008.5.1.4.1.1.1"
        raw.SOPInstanceUID = "1.2.3"
        raw.StudyInstanceUID = "1.2.3.4"
        raw.SeriesInstanceUID = "1.2.3.4.5"
        raw.Modality = "CR"
        study = study_by_key("p101-cxr-2026-09-11")
        retag_instance(raw, study, 0)
        blob = " ".join(
            str(elem.value) for elem in raw.iterall() if elem.keyword != "PixelData"
        )
        self.assertNotIn("Keller", blob)
        self.assertNotIn("Elisabeth", blob)
        self.assertNotIn("MRN-4471902", blob)
        self.assertNotIn("+41", blob)
        self.assertEqual(str(raw.PatientID), "p_101")
        self.assertEqual(str(raw.PatientName), "")
        self.assertEqual(raw.StudyInstanceUID, study.study_uid)
        self.assertEqual(raw.SOPInstanceUID, study.instance_uid(0))

    def test_missing_source_refuses_ellipses(self):
        from dicom_seed import source_instances

        study = study_by_key("p101-cxr-2026-09-11")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                source_instances(study, Path(tmp))

    def test_store_requires_parent_study(self):
        from dicom_seed import OrthancClient

        client = OrthancClient("http://orthanc.test", "u", "p")
        with patch.object(client, "_open", return_value={"Status": "Success"}):
            with self.assertRaises(RuntimeError):
                client.store(b"DICM")


if __name__ == "__main__":
    unittest.main()
