"""VISTA-3D mask → DICOM SEG on the source CT. No text model, no second volume."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import numpy as np

UID_NS = UUID("b7c2d8e1-4a5f-4e6b-9c0d-1f2a3b4c5d6e")
SERIES_DESCRIPTION = "VISTA-3D"
VISTA_LABELS: dict[int, str] = {
    1: "liver",
    2: "kidney",
    3: "spleen",
    4: "pancreas",
    5: "right kidney",
    6: "aorta",
    7: "inferior vena cava",
    8: "right adrenal gland",
    9: "left adrenal gland",
    10: "gallbladder",
    11: "esophagus",
    12: "stomach",
    13: "duodenum",
    14: "left kidney",
    15: "bladder",
    16: "prostate or uterus",
    17: "portal vein and splenic vein",
    18: "rectum",
    19: "small bowel",
    20: "lung",
    21: "bone",
    22: "brain",
    23: "lung tumor",
    24: "pancreatic tumor",
    25: "hepatic vessel",
    26: "hepatic tumor",
    27: "colon cancer primaries",
    28: "left lung upper lobe",
    29: "left lung lower lobe",
    30: "right lung upper lobe",
    31: "right lung middle lobe",
    32: "right lung lower lobe",
    57: "trachea",
    108: "left atrial appendage",
    115: "heart",
    119: "pulmonary vein",
    132: "airway",
}
ALLOWED_CLASSES = frozenset(VISTA_LABELS.values())
_SCT: dict[str, tuple[str, str]] = {
    "heart": ("80891009", "Heart"),
    "liver": ("10200004", "Liver"),
    "spleen": ("78961009", "Spleen"),
    "lung": ("39607008", "Lung"),
    "aorta": ("15825003", "Aorta"),
    "kidney": ("64033007", "Kidney"),
    "pancreas": ("15776009", "Pancreas"),
    "brain": ("12738006", "Brain"),
    "trachea": ("44567001", "Trachea"),
    "bladder": ("89837001", "Urinary bladder"),
    "stomach": ("69695003", "Stomach"),
}


def dicom_uid(*parts: str) -> str:
    return "2.25." + str(int(uuid5(UID_NS, "/".join(parts)).hex, 16))


def vista_series_uid(study_key: str) -> str:
    return dicom_uid("series", f"{study_key}-vista")


def study_key_from_source(source_id: str) -> str:
    return source_id.rsplit("/", 1)[-1]


def vista_report_source(study_source_id: str) -> str:
    key = study_key_from_source(study_source_id)
    ns = study_source_id.split("/", 1)[0] if "/" in study_source_id else "seed-demo"
    return f"{ns}/DiagnosticReport/{key}-vista"


def report_text(classes: tuple[str, ...]) -> str:
    names = ", ".join(classes) if classes else "anatomy"
    return f"VISTA-3D overlay on CT: {names}. Toggle the segmentation in the study viewer."


def normalize_classes(
    requested: list[str] | tuple[str, ...] | None,
    *,
    default: tuple[str, ...] = ("heart",),
) -> tuple[str, ...]:
    if not requested:
        return default
    cleaned = tuple(item.strip().lower() for item in requested if item and item.strip())
    unknown = [item for item in cleaned if item not in ALLOWED_CLASSES]
    if unknown:
        raise ValueError("unknown vista class: " + ", ".join(unknown))
    return cleaned or default


@dataclass(frozen=True)
class OverlayResult:
    seg_bytes: bytes
    classes: tuple[str, ...]
    report_text: str
    series_uid: str


def parse_vista_mask(raw: bytes) -> np.ndarray:
    if not raw:
        raise ValueError("empty vista body")
    blob = _unwrap_payload(raw)
    volume = _load_volume(blob)
    if volume.ndim == 2:
        volume = volume[np.newaxis, ...]
    if volume.ndim == 4:
        volume = volume[..., 0]
    if volume.ndim != 3:
        raise ValueError(f"vista mask must be 3D, got {volume.shape}")
    return np.asarray(volume)


def build_overlay(
    mask_bytes: bytes,
    source_files: list[bytes],
    *,
    classes: tuple[str, ...],
    study_key: str,
) -> OverlayResult:
    if not source_files:
        raise ValueError("no source CT instances")
    sources = _read_sources(source_files)
    mask = parse_vista_mask(mask_bytes)
    rows = int(sources[0].Rows)
    cols = int(sources[0].Columns)
    aligned = resample_nearest(mask, (len(sources), rows, cols))
    present = _classes_in_mask(aligned, classes)
    seg = _segmentation(sources, aligned, present, study_key)
    buf = io.BytesIO()
    try:
        seg.save_as(buf, write_like_original=False)
    except TypeError:
        seg.save_as(buf, enforce_file_format=True)
    return OverlayResult(
        seg_bytes=buf.getvalue(),
        classes=present,
        report_text=report_text(present),
        series_uid=str(seg.SeriesInstanceUID),
    )


def resample_nearest(volume: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    if tuple(volume.shape) == shape:
        return volume.astype(np.uint16, copy=False)
    zi = np.linspace(0, volume.shape[0] - 1, shape[0]).round().astype(int)
    yi = np.linspace(0, volume.shape[1] - 1, shape[1]).round().astype(int)
    xi = np.linspace(0, volume.shape[2] - 1, shape[2]).round().astype(int)
    return volume[np.ix_(zi, yi, xi)].astype(np.uint16, copy=False)


def _unwrap_payload(raw: bytes) -> bytes:
    stripped = raw.lstrip()
    if stripped[:1] in b"{[":
        payload: Any = json.loads(stripped)
        if isinstance(payload, dict):
            for key in ("image", "mask", "data", "segmentation", "output"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    extra = value.split(",", 1)[-1] if value.startswith("data:") else value
                    try:
                        return base64.b64decode(extra)
                    except Exception:
                        continue
        raise ValueError("json vista body has no mask")
    if stripped[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            suffixes = (".nii", ".nii.gz", ".nrrd", ".seg.nrrd")
            name = next((item for item in bundle.namelist() if item.endswith(suffixes)), None)
            if name is None:
                raise ValueError("zip vista body has no volume")
            return bundle.read(name)
    return raw


def _load_volume(blob: bytes) -> np.ndarray:
    import nibabel as nib

    suffix = ".nrrd" if blob[:4] == b"NRRD" else ".nii.gz"
    path = Path(f"/tmp/vista-mask-{uuid4().hex}{suffix}")
    try:
        path.write_bytes(blob)
        img = nib.load(str(path))
        data = np.asanyarray(img.dataobj)
    finally:
        path.unlink(missing_ok=True)
    if data.ndim >= 3:
        data = np.transpose(data, (2, 1, 0))
    return data


def _read_sources(files: list[bytes]):
    import pydicom

    datasets = [pydicom.dcmread(io.BytesIO(item), force=True) for item in files]
    datasets = [ds for ds in datasets if str(getattr(ds, "Modality", "")).upper() != "SEG"]
    if not datasets:
        raise ValueError("no CT instances in source files")

    def _key(ds) -> tuple[float, int]:
        position = getattr(ds, "ImagePositionPatient", None)
        depth = float(position[2]) if position is not None and len(position) > 2 else 0.0
        number = int(getattr(ds, "InstanceNumber", 0) or 0)
        return (depth, number)

    datasets.sort(key=_key)
    for ds in datasets:
        if not getattr(ds, "PatientBirthDate", None):
            ds.PatientBirthDate = ""
        if not getattr(ds, "PatientSex", None):
            ds.PatientSex = ""
        if not getattr(ds, "PatientName", None):
            ds.PatientName = ""
        if not getattr(ds, "PatientID", None):
            ds.PatientID = "p360"
        if not getattr(ds, "StudyDate", None):
            ds.StudyDate = "20260101"
        if not getattr(ds, "StudyTime", None):
            ds.StudyTime = "000000"
        if not getattr(ds, "StudyID", None):
            ds.StudyID = "1"
        if not getattr(ds, "AccessionNumber", None):
            ds.AccessionNumber = ""
    return datasets


def _classes_in_mask(mask: np.ndarray, classes: tuple[str, ...]) -> tuple[str, ...]:
    values = {int(v) for v in np.unique(mask) if int(v) != 0}
    if not values:
        return classes
    if values <= {1} and len(classes) == 1:
        return classes
    named = tuple(VISTA_LABELS[v] for v in sorted(values) if v in VISTA_LABELS)
    if named:
        return named
    return classes


def _segmentation(sources, mask: np.ndarray, classes: tuple[str, ...], study_key: str):
    from highdicom import AlgorithmIdentificationSequence
    from highdicom.seg import Segmentation, SegmentDescription
    from highdicom.seg.enum import SegmentAlgorithmTypeValues, SegmentationTypeValues
    from highdicom.sr.coding import CodedConcept
    from pydicom.uid import generate_uid

    if not classes:
        classes = ("heart",)
    frames = []
    descriptions = []
    for index, name in enumerate(classes, start=1):
        if len(classes) == 1:
            present = mask > 0
        else:
            label = next((key for key, value in VISTA_LABELS.items() if value == name), None)
            present = (mask == label) if label is not None else mask > 0
        frames.append(present.astype(np.uint8))
        code, meaning = _SCT.get(name, ("123037004", name))
        descriptions.append(
            SegmentDescription(
                segment_number=index,
                segment_label=name,
                segmented_property_category=CodedConcept("123037004", "SCT", "Anatomical Structure"),
                segmented_property_type=CodedConcept(code, "SCT", meaning),
                algorithm_type=SegmentAlgorithmTypeValues.AUTOMATIC,
                algorithm_identification=AlgorithmIdentificationSequence(
                    name="VISTA-3D",
                    family=CodedConcept("123109000", "SCT", "Artificial intelligence"),
                    version="1.0.0",
                ),
            )
        )
    pixel = np.stack(frames, axis=0)
    if pixel.shape[0] == 1:
        pixel = pixel[0]
    return Segmentation(
        source_images=sources,
        pixel_array=pixel.astype(bool),
        segmentation_type=SegmentationTypeValues.BINARY,
        segment_descriptions=descriptions,
        series_instance_uid=vista_series_uid(study_key),
        series_number=100,
        sop_instance_uid=generate_uid(),
        instance_number=1,
        manufacturer="NVIDIA",
        manufacturer_model_name="VISTA-3D",
        software_versions="1.0.0",
        device_serial_number="patient360",
        series_description=SERIES_DESCRIPTION,
    )
