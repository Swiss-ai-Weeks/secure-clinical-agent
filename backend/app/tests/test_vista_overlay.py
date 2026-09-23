from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian

from patient360.vista_overlay import build_overlay, parse_vista_mask, report_text, vista_series_uid

STUDY_UID = "2.25.111111111111111111111111111111"
SERIES_UID = "2.25.222222222222222222222222222222"


def _ct_file(index: int, *, rows: int = 8, cols: int = 8) -> bytes:
    meta = Dataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    meta.MediaStorageSOPInstanceUID = f"2.25.33333333333333333333333333333{index}"
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = "2.25.360012345678901234567890123456"
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\x00" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = STUDY_UID
    ds.SeriesInstanceUID = SERIES_UID
    ds.Modality = "CT"
    ds.PatientID = "p_102"
    ds.PatientName = "p102"
    ds.PatientBirthDate = ""
    ds.PatientSex = ""
    ds.StudyDate = "20260701"
    ds.SeriesNumber = 1
    ds.InstanceNumber = index + 1
    ds.Rows = rows
    ds.Columns = cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.RescaleIntercept = -1024
    ds.RescaleSlope = 1
    ds.SliceThickness = 2.5
    ds.ImagePositionPatient = [0.0, 0.0, float(index * 2.5)]
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.PixelSpacing = [1.0, 1.0]
    ds.FrameOfReferenceUID = "2.25.444444444444444444444444444444"
    ds.PixelData = b"\x00\x00" * (rows * cols)
    buf = io.BytesIO()
    try:
        ds.save_as(buf, write_like_original=False)
    except TypeError:
        ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def _nifti_bytes(volume: np.ndarray) -> bytes:
    import nibabel as nib

    img = nib.Nifti1Image(np.transpose(volume.astype(np.uint8), (2, 1, 0)), np.eye(4))
    path = Path(f"/tmp/vista-test-{volume.shape}.nii.gz")
    nib.save(img, str(path))
    try:
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def test_report_text_names_classes():
    text = report_text(("heart",))
    assert "heart" in text
    assert "320 bytes" not in text


def test_build_overlay_references_source_ct():
    sources = [_ct_file(index) for index in range(4)]
    mask = np.zeros((4, 8, 8), dtype=np.uint8)
    mask[:, 2:6, 2:6] = 1
    overlay = build_overlay(_nifti_bytes(mask), sources, classes=("heart",), study_key="p102-ct-2026-07-01")
    ds = pydicom.dcmread(io.BytesIO(overlay.seg_bytes), force=True)
    assert ds.StudyInstanceUID == STUDY_UID
    assert ds.Modality == "SEG"
    assert ds.SeriesInstanceUID == vista_series_uid("p102-ct-2026-07-01")
    referenced = {
        str(item.ReferencedSOPInstanceUID)
        for seq in ds.ReferencedSeriesSequence
        for item in seq.ReferencedInstanceSequence
    }
    assert referenced == {f"2.25.33333333333333333333333333333{index}" for index in range(4)}
    assert overlay.classes == ("heart",)
    assert "heart" in overlay.report_text


def test_parse_vista_mask_roundtrip():
    mask = np.zeros((2, 4, 4), dtype=np.uint8)
    mask[1, 1, 1] = 1
    parsed = parse_vista_mask(_nifti_bytes(mask))
    assert parsed.shape == (2, 4, 4)
    assert int(parsed[1, 1, 1]) == 1
