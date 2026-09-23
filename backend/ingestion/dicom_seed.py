#!/usr/bin/env python3
"""Store retagged public DICOM in Orthanc and link clinical.studies.orthanc_id.

The ellipse renderer stays for offline tests. The live command refuses to store
those pixels when a public source file is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from imaging_catalog import LOINC, STUDIES, DemoStudy, sid

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ROOT / "backend" / "deploy" / "patient360" / ".env"
DEFAULT_DATA_DIR = ROOT / ".data" / "imaging"
DEFAULT_SOURCES_DIR = DEFAULT_DATA_DIR / "sources"
MAX_SOURCE_INSTANCES = 160

# Single-frame public-domain samples (chest radiograph and cardiac ultrasound).
SOURCE_URLS = {
    "cr-chest.dcm": "https://downloads.openmicroscopy.org/images/DICOM/samples/CR-MONO1-10-chest.dcm",
    "us-echo.dcm": "https://downloads.openmicroscopy.org/images/DICOM/samples/US-MONO2-8-8x-execho.dcm",
}
# Real multi-slice series from TCIA. De-identified, CC BY. Identity tags are stripped again before storage.
SERIES_ZIPS = {
    "ct-chest-lidc": (
        "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage"
        "?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6279.6001.179049373636438705059720603192",
        "LIDC-IDRI chest CT, 133 slices. CC BY 3.0. https://www.cancerimagingarchive.net/collection/lidc-idri/",
    ),
    "mr-brain-upenn": (
        "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage"
        "?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.74959210626421264963078150067043317963",
        "UPENN-GBM axial T2 FLAIR, 60 slices. CC BY 4.0. https://www.cancerimagingarchive.net/collection/upenn-gbm/",
    ),
}
SOURCE_LICENSE = (
    "Chest radiograph and ultrasound: public domain, Sebastien Barre via Open Microscopy. "
    "Chest CT: LIDC-IDRI, CC BY 3.0. Brain MRI: UPENN-GBM, CC BY 4.0. "
    "Identity tags are stripped again before storage. Files stay local and are not redistributed."
)

_IDENTITY_KEYWORDS = {
    "PatientName",
    "PatientBirthDate",
    "PatientBirthTime",
    "PatientSex",
    "PatientAge",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "OtherPatientIDs",
    "OtherPatientNames",
    "PatientMotherBirthName",
    "PatientBirthName",
    "EthnicGroup",
    "PatientComments",
    "InstitutionName",
    "InstitutionAddress",
    "ReferringPhysicianName",
    "PerformingPhysicianName",
    "OperatorsName",
    "NameOfPhysiciansReadingStudy",
    "AccessionNumber",
}


def _jsonb(value: dict[str, Any]):
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _pixels(study: DemoStudy, index: int) -> list[int]:
    rows, cols = study.rows, study.cols
    out = [0] * (rows * cols)
    cy, cx = rows // 2, cols // 2
    if study.modality == "CR":
        for y in range(rows):
            for x in range(cols):
                left = ((x - cols * 0.32) ** 2) / (cols * 0.18) ** 2 + ((y - cy) ** 2) / (rows * 0.32) ** 2
                right = ((x - cols * 0.68) ** 2) / (cols * 0.18) ** 2 + ((y - cy) ** 2) / (rows * 0.32) ** 2
                value = 900
                if left <= 1 or right <= 1:
                    value = 180
                if abs(x - cx) < cols * 0.06:
                    value = 1100
                out[y * cols + x] = value
    elif study.modality == "CT":
        radius = min(rows, cols) * 0.38
        organ = min(rows, cols) * 0.16
        oz = 7
        for y in range(rows):
            for x in range(cols):
                dx, dy, dz = x - cx, y - cy, index - oz
                if dx * dx + dy * dy > radius * radius:
                    value = -1000
                elif (x - cx - 8) ** 2 + (y - cy + 4) ** 2 + dz * dz * 2 <= organ * organ:
                    value = 60
                else:
                    value = 30
                out[y * cols + x] = value
    else:
        for y in range(rows):
            for x in range(cols):
                r2 = (x - cx) ** 2 + (y - cy) ** 2
                out[y * cols + x] = max(0, 1400 - r2 // 8)
    return out


def render_instance(study: DemoStudy, index: int):
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import ExplicitVRLittleEndian
    pixels = _pixels(study, index)
    intercept = -1024 if study.modality == "CT" else 0
    stored = [max(0, min(4095, value - intercept)) for value in pixels]
    meta = Dataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2" if study.modality == "CT" else (
        "1.2.840.10008.5.1.4.1.1.1" if study.modality == "CR" else "1.2.840.10008.5.1.4.1.1.6.1"
    )
    meta.MediaStorageSOPInstanceUID = study.instance_uid(index)
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = dicom_impl_uid()
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\x00" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = study.instance_uid(index)
    ds.StudyInstanceUID = study.study_uid
    ds.SeriesInstanceUID = study.series_uid
    ds.Modality = study.modality
    ds.PatientID = study.patient_key
    ds.PatientName = study.patient_key.replace("_", "")
    ds.PatientBirthDate = ""
    ds.PatientSex = ""
    ds.StudyDate = study.study_at.strftime("%Y%m%d")
    ds.StudyTime = study.study_at.strftime("%H%M%S")
    ds.StudyDescription = study.description
    ds.SeriesDescription = study.procedure_display
    ds.SeriesNumber = 1
    ds.InstanceNumber = index + 1
    ds.Rows = study.rows
    ds.Columns = study.cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    if study.modality == "CT":
        ds.RescaleIntercept = intercept
        ds.RescaleSlope = 1
        ds.SliceThickness = 2.5
        ds.ImagePositionPatient = [0.0, 0.0, float(index * 2.5)]
        ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        ds.PixelSpacing = [1.0, 1.0]
    ds.PixelData = b"".join(int(v).to_bytes(2, "little") for v in stored)
    return ds


def dicom_impl_uid() -> str:
    return "2.25.360012345678901234567890123456"


def retag_instance(ds, study: DemoStudy, index: int):
    """Replace identity and study identifiers. Pixel bytes stay as read."""
    drop = [
        elem.tag
        for elem in list(ds)
        if elem.keyword in _IDENTITY_KEYWORDS or (elem.tag.group == 0x0010 and elem.keyword != "PatientID")
    ]
    for tag in drop:
        if tag in ds:
            del ds[tag]
    ds.PatientID = study.patient_key
    ds.PatientName = ""
    ds.PatientBirthDate = ""
    ds.PatientSex = ""
    ds.StudyInstanceUID = study.study_uid
    ds.SeriesInstanceUID = study.series_uid
    ds.SOPInstanceUID = study.instance_uid(index)
    ds.StudyDate = study.study_at.strftime("%Y%m%d")
    ds.StudyTime = study.study_at.strftime("%H%M%S")
    ds.StudyDescription = study.description
    ds.SeriesDescription = study.procedure_display
    ds.Modality = study.modality
    ds.SeriesNumber = 1
    ds.InstanceNumber = index + 1
    file_meta = getattr(ds, "file_meta", None)
    if file_meta is not None:
        file_meta.MediaStorageSOPInstanceUID = study.instance_uid(index)
        if getattr(ds, "SOPClassUID", None):
            file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        file_meta.ImplementationClassUID = dicom_impl_uid()
    return ds


def dataset_bytes(ds) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    try:
        ds.save_as(buf, write_like_original=False)
    except TypeError:
        ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def _dicom_files(directory: Path) -> list[Path]:
    files = [item for item in directory.rglob("*") if item.is_file() and item.suffix.lower() in {".dcm", ""}]
    dicom: list[Path] = []
    for item in files:
        if item.suffix.lower() == ".dcm":
            dicom.append(item)
            continue
        try:
            blob = item.read_bytes()[:132]
        except OSError:
            continue
        if b"DICM" in blob:
            dicom.append(item)
    return dicom


def _series_slice(paths: list[Path]) -> list[Path]:
    """Keep the largest series, in instance order, capped so a demo volume stays one stack."""
    import pydicom

    grouped: dict[str, list[tuple[int, float, Path]]] = {}
    for path in paths:
        ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
        series = str(getattr(ds, "SeriesInstanceUID", "") or "series")
        number = int(getattr(ds, "InstanceNumber", 0) or 0)
        position = getattr(ds, "ImagePositionPatient", None)
        depth = float(position[2]) if position is not None and len(position) > 2 else float(number)
        grouped.setdefault(series, []).append((number, depth, path))
    chosen = max(grouped.values(), key=len)
    chosen.sort(key=lambda item: (item[0], item[1], item[2].name))
    return [path for _number, _depth, path in chosen[:MAX_SOURCE_INSTANCES]]


def source_instances(study: DemoStudy, sources_dir: Path) -> list[Path]:
    if not study.source_file:
        raise FileNotFoundError(f"refusing synthetic pixels for {study.key}")
    path = sources_dir / study.source_file
    if path.is_file():
        return [path]
    if path.is_dir():
        files = _dicom_files(path)
        if files:
            return _series_slice(files)
    raise FileNotFoundError(f"missing DICOM source {path}; refusing synthetic pixels")


def retag_file(study: DemoStudy, path: Path, index: int) -> bytes:
    import pydicom

    ds = pydicom.dcmread(str(path), force=True)
    retag_instance(ds, study, index)
    return dataset_bytes(ds)


def _download(url: str, target: Path, *, timeout: int) -> None:
    req = Request(url)
    try:
        with urlopen(req, timeout=timeout) as resp:
            target.write_bytes(resp.read())
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"could not download {target.name}: {exc}") from exc
    if target.stat().st_size == 0:
        raise RuntimeError(f"downloaded {target.name} was empty")


def _extract_zip(archive: Path, destination: Path) -> None:
    import zipfile

    if not zipfile.is_zipfile(archive):
        raise RuntimeError(f"{archive.name} is not a zip of DICOM instances")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)


def ensure_sources(directory: Path) -> Path:
    """Download public samples once and record where they came from."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCE_URLS.items():
        target = directory / name
        if target.is_file() and target.stat().st_size > 0:
            continue
        _download(url, target, timeout=60)
    for name, (url, _note) in SERIES_ZIPS.items():
        folder = directory / name
        if _dicom_files(folder) if folder.is_dir() else []:
            continue
        archive = directory / f"{name}.zip"
        if not archive.is_file() or archive.stat().st_size == 0:
            _download(url, archive, timeout=300)
        _extract_zip(archive, folder)
        if not _dicom_files(folder):
            raise RuntimeError(f"{name} zip contained no DICOM instances")
    manifest = {
        "license": SOURCE_LICENSE,
        "files": {name: url for name, url in SOURCE_URLS.items()},
        "series": {name: {"url": url, "note": note} for name, (url, note) in SERIES_ZIPS.items()},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return directory


def instance_bytes(study: DemoStudy, index: int) -> bytes:
    from io import BytesIO

    ds = render_instance(study, index)
    buf = BytesIO()
    try:
        ds.save_as(buf, write_like_original=False)
    except TypeError:
        ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def write_local_series(study: DemoStudy, directory: Path) -> Path:
    target = directory / study.key
    target.mkdir(parents=True, exist_ok=True)
    for index in range(study.slices):
        path = target / f"{index + 1:04d}.dcm"
        path.write_bytes(instance_bytes(study, index))
    return target


class OrthancClient:
    def __init__(self, url: str, user: str, password: str) -> None:
        self.url = url.rstrip("/")
        self.auth = (user, password)

    def _open(
        self,
        path: str,
        data: bytes | None = None,
        content_type: str | None = None,
        method: str | None = None,
    ) -> Any:
        import base64

        user, password = self.auth
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers = {"Authorization": f"Basic {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        verb = method or ("POST" if data is not None else "GET")
        req = Request(f"{self.url}{path}", data=data, headers=headers, method=verb)
        try:
            with urlopen(req, timeout=30) as resp:
                body = resp.read()
        except HTTPError as exc:
            raise RuntimeError(f"orthanc {path} http={exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"orthanc unreachable: {exc.reason}") from exc
        if not body:
            return None
        if body[:1] in b"[{":
            return json.loads(body.decode())
        return body

    def drop_study(self, study_uid: str) -> None:
        """Remove a previous study with this UID so a re-seed can replace its pixels."""
        try:
            found = self._open("/tools/lookup", study_uid.encode(), "text/plain")
        except RuntimeError as exc:
            if "http=404" in str(exc):
                return
            raise
        ident = ""
        if isinstance(found, list) and found:
            row = found[0]
            ident = str(row.get("ID") or "") if isinstance(row, dict) else str(row)
        elif isinstance(found, dict):
            ident = str(found.get("ID") or "")
        elif isinstance(found, str):
            ident = found
        if ident:
            self._open(f"/studies/{ident}", method="DELETE")

    def store(self, payload: bytes) -> dict[str, Any]:
        body = self._open("/instances", payload, "application/dicom")
        if not isinstance(body, dict) or not body.get("ParentStudy"):
            raise RuntimeError("orthanc store did not return ParentStudy")
        return body

    def system(self) -> dict[str, Any]:
        body = self._open("/system")
        if not isinstance(body, dict):
            raise RuntimeError("orthanc /system failed")
        return body


def _encounter_id(seeder: Any, study: DemoStudy):
    if study.encounter_key == "latest":
        row = seeder.conn.execute(
            "SELECT id FROM clinical.encounters WHERE patient_key = %s "
            "ORDER BY started_at DESC NULLS LAST LIMIT 1",
            (study.patient_key,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"missing encounter for {study.patient_key}")
        return row[0]
    cached = seeder.ids.get(f"Encounter/{study.encounter_key}")
    if cached is not None:
        return cached
    row = seeder.conn.execute(
        "SELECT id FROM clinical.encounters WHERE source_id = %s",
        (sid("Encounter", study.encounter_key),),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"missing encounter {study.encounter_key}; run seed_demo first")
    seeder.ids[f"Encounter/{study.encounter_key}"] = row[0]
    return row[0]


def upsert_clinical(seeder, study: DemoStudy, *, orthanc_id: str | None, instances: int) -> None:
    seeder.upsert(
        "studies",
        f"ImagingStudy/{study.key}",
        dict(
            source_id=study.study_source,
            patient_key=study.patient_key,
            encounter_id=_encounter_id(seeder, study),
            status="available",
            study_at=study.study_at,
            modality=study.modality,
            description=study.description,
            series_count=1 if instances else None,
            instance_count=instances or None,
            procedure_code=study.procedure_code,
            procedure_system=LOINC,
            procedure_display=study.procedure_display,
            orthanc_id=orthanc_id,
            confidentiality="N",
            sensitivity=[],
            resource=_jsonb({"resourceType": "ImagingStudy", "status": "available"}),
        ),
    )
    seeder.upsert(
        "diagnostic_reports",
        f"DiagnosticReport/{study.key}",
        dict(
            source_id=study.report_source,
            patient_key=study.patient_key,
            encounter_id=_encounter_id(seeder, study),
            status="final",
            category="RAD" if study.modality == "CR" else study.modality,
            code=study.procedure_code,
            code_system=LOINC,
            display=study.procedure_display,
            effective_at=study.study_at,
            issued_at=study.study_at,
            conclusion_text=study.conclusion_text,
            study_id=seeder.ids[f"ImagingStudy/{study.key}"],
            report_ref=study.report_ref,
            confidentiality="N",
            sensitivity=[],
            resource=_jsonb(
                {
                    "resourceType": "DiagnosticReport",
                    "status": "final",
                    "category": "RAD" if study.modality == "CR" else study.modality,
                }
            ),
        ),
    )


def study_payloads(
    study: DemoStudy,
    data_dir: Path,
    sources_dir: Path | None,
    *,
    require_files: bool,
) -> list[bytes]:
    if study.source_file:
        if sources_dir is None:
            raise FileNotFoundError(f"missing DICOM source for {study.key}; refusing synthetic pixels")
        paths = source_instances(study, sources_dir)
        return [retag_file(study, path, index) for index, path in enumerate(paths)]
    if require_files:
        raise FileNotFoundError(f"refusing synthetic pixels for {study.key}")
    folder = write_local_series(study, data_dir)
    return [(folder / f"{index + 1:04d}.dcm").read_bytes() for index in range(study.slices)]


def seed(
    *,
    dsn: str,
    orthanc: OrthancClient,
    data_dir: Path,
    studies: tuple[DemoStudy, ...] = STUDIES,
    sources_dir: Path | None = None,
    require_files: bool = False,
) -> dict[str, Any]:
    import psycopg

    from seed_demo import Seeder

    linked: list[dict[str, Any]] = []
    with psycopg.connect(dsn) as conn:
        seeder = Seeder(conn)
        with conn.transaction():
            for study in studies:
                payloads = study_payloads(
                    study, data_dir, sources_dir, require_files=require_files
                )
                if study.source_file:
                    orthanc.drop_study(study.study_uid)
                last: dict[str, Any] | None = None
                for payload in payloads:
                    last = orthanc.store(payload)
                assert last is not None
                upsert_clinical(
                    seeder,
                    study,
                    orthanc_id=str(last["ParentStudy"]),
                    instances=len(payloads),
                )
                linked.append(
                    {
                        "patient_key": study.patient_key,
                        "source_id": study.study_source,
                        "orthanc_id": last["ParentStudy"],
                        "instances": len(payloads),
                        "vista_path": f"/data/patient360/{study.key}" if study.vista_classes else None,
                    }
                )
    return {"ok": True, "studies": linked}


def _orthanc_from_env(env: dict[str, str]) -> OrthancClient:
    url = env.get("PATIENT360_ORTHANC_URL", "http://127.0.0.1:8042")
    if url.startswith("http://orthanc"):
        url = "http://127.0.0.1:8042"
    user = env.get("PATIENT360_ORTHANC_USER", "orthanc")
    password = env.get("PATIENT360_ORTHANC_PASSWORD", "orthanc")
    return OrthancClient(url, user, password)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    ap.add_argument("--dsn")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = ap.parse_args(argv)
    from seed_demo import load_env_file

    env = {**load_env_file(args.env_file), **os.environ}
    dsn = (
        args.dsn
        or env.get("PATIENT360_WORKER_DSN")
        or (
            f"postgres://p360_worker:{env.get('PATIENT360_WORKER_PASSWORD', 'patient360-worker-dev')}"
            f"@{env.get('PATIENT360_PG_HOST', '127.0.0.1')}:{env.get('PATIENT360_PG_PORT', '5432')}/fhir"
        )
    )
    client = _orthanc_from_env(env)
    client.system()
    sources = ensure_sources(args.data_dir / "sources")
    result = seed(
        dsn=dsn,
        orthanc=client,
        data_dir=args.data_dir,
        sources_dir=sources,
        require_files=True,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
