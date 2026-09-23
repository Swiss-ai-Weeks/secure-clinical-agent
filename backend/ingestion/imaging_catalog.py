"""Demo imaging studies to seed into Postgres and Orthanc.

Live pixels come from public-domain DICOM samples. Headers are retagged with the opaque
patient key before Orthanc stores them. The ellipse renderer remains for offline tests.
VISTA-3D only has a CT volume (p_102); MedGemma can describe any preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid5

LOINC = "http://loinc.org"
SRC = "seed-demo"
UID_NS = UUID("b7c2d8e1-4a5f-4e6b-9c0d-1f2a3b4c5d6e")


def sid(kind: str, key: str) -> str:
    return f"{SRC}/{kind}/{key}"


def dicom_uid(*parts: str) -> str:
    """Numeric UID derived from stable parts. Re-seeding keeps the same SOP."""
    return "2.25." + str(int(uuid5(UID_NS, "/".join(parts)).hex, 16))


def ts(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DemoStudy:
    patient_key: str
    key: str
    encounter_key: str
    modality: str
    procedure_code: str
    procedure_display: str
    study_at: datetime
    description: str
    conclusion_text: str
    rows: int
    cols: int
    slices: int
    report_ref: str
    source_file: str = ""
    vista_classes: tuple[str, ...] = ()

    @property
    def study_source(self) -> str:
        return sid("ImagingStudy", self.key)

    @property
    def report_source(self) -> str:
        return sid("DiagnosticReport", self.key)

    @property
    def vlm_source(self) -> str:
        return sid("DiagnosticReport", f"{self.key}-vlm")

    @property
    def vista_source(self) -> str:
        return sid("DiagnosticReport", f"{self.key}-vista")

    @property
    def study_uid(self) -> str:
        return dicom_uid("study", self.key)

    @property
    def series_uid(self) -> str:
        return dicom_uid("series", self.key)

    def instance_uid(self, index: int) -> str:
        return dicom_uid("instance", self.key, str(index))


def pdf_object_key(patient_key: str, key: str) -> str:
    return f"notes/{patient_key}/{key}.pdf"


STUDIES: tuple[DemoStudy, ...] = (
    DemoStudy(
        patient_key="p_101",
        key="p101-cxr-2026-09-11",
        encounter_key="p101-imp-2026-09-10",
        modality="CR",
        procedure_code="36643-5",
        procedure_display="Chest X-ray",
        study_at=ts(2026, 9, 11, 9),
        description="Frontal chest radiograph",
        conclusion_text="No acute cardiopulmonary process.",
        rows=256,
        cols=256,
        slices=1,
        report_ref=pdf_object_key("p_101", "p101-cxr-2026-09-11"),
        source_file="cr-chest.dcm",
    ),
    DemoStudy(
        patient_key="p_102",
        key="p102-ct-2026-07-01",
        encounter_key="p102-amb-2026-07-01",
        modality="CT",
        procedure_code="24627-2",
        procedure_display="CT Chest",
        study_at=ts(2026, 7, 1, 10, 10),
        description="Chest CT",
        conclusion_text="CT chest. Formal radiologist interpretation pending.",
        rows=64,
        cols=64,
        slices=16,
        report_ref=pdf_object_key("p_102", "p102-ct-2026-07-01"),
        source_file="ct-chest-lidc",
        vista_classes=("heart",),
    ),
    DemoStudy(
        patient_key="p_102",
        key="p102-mr-2026-07-02",
        encounter_key="p102-amb-2026-07-01",
        modality="MR",
        procedure_code="24590-2",
        procedure_display="MRI Brain",
        study_at=ts(2026, 7, 2, 11),
        description="Brain MRI",
        conclusion_text="MRI brain. Formal radiologist interpretation pending.",
        rows=64,
        cols=64,
        slices=1,
        report_ref=pdf_object_key("p_102", "p102-mr-2026-07-02"),
        source_file="mr-brain-upenn",
    ),
    DemoStudy(
        patient_key="p_103",
        key="p103-us-2026-05-20",
        encounter_key="p103-amb-2026-05-20",
        modality="US",
        procedure_code="34552-0",
        procedure_display="US Heart",
        study_at=ts(2026, 5, 20, 11, 20),
        description="Cardiac ultrasound",
        conclusion_text="Cardiac ultrasound. Formal interpretation pending.",
        rows=192,
        cols=192,
        slices=1,
        report_ref=pdf_object_key("p_103", "p103-us-2026-05-20"),
        source_file="us-echo.dcm",
    ),
    DemoStudy(
        patient_key="p_485ba8c8597d4c5cb0fbda55317119a3",
        key="hettinger-cxr-2026-09-22",
        encounter_key="latest",
        modality="CR",
        procedure_code="36643-5",
        procedure_display="Chest X-ray",
        study_at=ts(2026, 9, 22, 8, 30),
        description="Frontal chest radiograph",
        conclusion_text="No acute cardiopulmonary process.",
        rows=256,
        cols=256,
        slices=1,
        report_ref=pdf_object_key("p_485ba8c8597d4c5cb0fbda55317119a3", "hettinger-cxr-2026-09-22"),
        source_file="cr-chest.dcm",
    ),
)


def study_by_key(key: str) -> DemoStudy:
    for study in STUDIES:
        if study.key == key:
            return study
    raise KeyError(key)
