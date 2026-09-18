#!/usr/bin/env python3
"""Hand-seeded demo personas and patients (Build Plan §7 step 1, §9).

Writes, idempotently (upsert on patient_key / source_id):
  identity.users     the seven personas (roles only; names live in the dev-login map)
  clinical.*         p_101 (labs trend, medication change, one V+PSY condition and one
                     R+PSY medication, food allergy, renal-diabetic diet order on ward
                     w_3b, one internal V+PSY note *metadata* row), p_102, p_103 (Maria:
                     meds, conditions, a booked cardiology appointment), p_205 (unassigned)
  vault              linkage/self/u_maria -> p_103 (the only place that link persists) and
                     linkage/identity/{p_xxx} synthetic identity records (`register`)
  audit.audit_events one `consent_granted` row (detail.seeded = true) per grant tuple that
                     openfga-init loads, so the portal can list and revoke them; one `ingest`
                     row, detail.kind = seed_demo

Grants are not written here: openfga-init loads tuples.demo.yaml. Note *text* is not
written here: notes stay published = false until the notes pipeline produces sanitized
text, so /tools/notes has nothing to leak in the meantime.

Run from the repository root with the backend's environment (it has psycopg):
  cd backend/app && uv run python ../ingestion/seed_demo.py
or
  uv run --with "psycopg[binary]" python backend/ingestion/seed_demo.py
Connection and vault settings come from backend/deploy/patient360/.env by default; the
vault writes use PATIENT360_LINKAGE_WORKER_TOKEN (create/update on linkage/*).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ROOT / "backend" / "deploy" / "patient360" / ".env"
SRC = "seed-demo"  # source namespace for source_id; never a Synthea id

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
UCUM = "http://unitsofmeasure.org"
CLINICAL_NOTE = "clinical-note"

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

USERS = [
    # user_id, role, department, credential_level
    ("u_chen", "attending", "internal-medicine", 3),
    ("u_rivera", "care_team", "ward-3b", 2),
    ("u_okafor", "consultant", "cardiology", 3),
    ("u_nair", "researcher", "research", 2),
    ("u_maria", "patient", None, 1),
    ("u_diego", "caregiver", None, 1),
    ("u_lindqvist", "dietary_staff", "kitchen", 1),
    ("u_haller", "caregiver", None, 1),  # Nina Haller, legal guardian of p_104 (guardian tuple)
]

PATIENTS = [
    # patient_key, sex, birth_year
    ("p_101", "female", 1961),
    ("p_102", "male", 1974),
    ("p_103", "female", 1958),
    ("p_104", "female", 2012),  # Lea Haller, 14: the minor with a confidential adolescent-clinic visit
    ("p_205", "male", 1989),
]

VAULT_LINKS = {"u_maria": "p_103"}

# `register` (Build Plan §4.5): synthetic identities for the demo patients, held only in the
# vault at linkage/identity/{patient_key}. The clinical store keeps sex and birth year; the API
# exposes the banner projection (names, full DOB, sex, MRN) to self and live relationships,
# and never address, phone, or national id. AHV-style numbers are synthetic.
IDENTITIES: dict[str, dict[str, Any]] = {
    "p_101": {
        "given_name": "Elisabeth",
        "family_name": "Keller",
        "birth_date": "1961-04-17",
        "sex": "female",
        "mrn": "MRN-4471902",
        "phone": "+41 44 555 01 17",
        "national_id": "756.1234.5678.97",
        "address": {"line": "Seestrasse 14", "postal_code": "8002", "city": "Zürich", "country": "CH"},
    },
    "p_102": {
        "given_name": "Marco",
        "family_name": "Bianchi",
        "birth_date": "1974-11-02",
        "sex": "male",
        "mrn": "MRN-4471903",
        "phone": "+41 91 555 02 02",
        "national_id": "756.2345.6789.08",
        "address": {"line": "Via Nassa 5", "postal_code": "6900", "city": "Lugano", "country": "CH"},
    },
    "p_103": {
        "given_name": "Maria",
        "family_name": "Santos",
        "birth_date": "1958-07-23",
        "sex": "female",
        "mrn": "MRN-4471904",
        "phone": "+41 22 555 03 23",
        "national_id": "756.3456.7890.19",
        "address": {"line": "Rue du Rhône 8", "postal_code": "1204", "city": "Genève", "country": "CH"},
    },
    "p_205": {
        "given_name": "Jonas",
        "family_name": "Weber",
        "birth_date": "1989-02-09",
        "sex": "male",
        "mrn": "MRN-4472051",
        "phone": "+41 31 555 05 09",
        "national_id": "756.4567.8901.20",
        "address": {"line": "Bundesplatz 3", "postal_code": "3011", "city": "Bern", "country": "CH"},
    },
    "p_104": {
        "given_name": "Lea",
        "family_name": "Haller",
        "birth_date": "2012-05-03",  # majority on 2030-05-03: the guardian tuple's expiry
        "sex": "female",
        "mrn": "MRN-4471905",
        "phone": "+41 44 555 04 03",
        "national_id": "756.5678.9012.31",
        "address": {"line": "Hardturmstrasse 22", "postal_code": "8005", "city": "Zürich", "country": "CH"},
    },
}

# Consent records for the grants openfga-init loads from tuples.demo.yaml (Build Plan §4.2:
# the consent_granted audit row is the record; the tuple is the enforcement). Windows mirror
# tuples.demo.yaml; seed_grants.py (Track B) will own this list. Patient-side grants on p_103
# are Maria's; staff assignments and the guardianship have no agent_user (the worker wrote
# them from the roster or the registration proof). Ids are deterministic so re-running the
# seed appends nothing (duplicate primary keys are skipped).
CONSENT_NAMESPACE = UUID("6f1d2b3a-9c7e-4a5b-8d21-0f3e5c7a9b11")
DEMO_GRANTS: list[tuple[str, str, str, str, str, str | None]] = [
    # grantee, relation, patient, start, expiry, granted_by
    ("u_chen", "attending", "p_101", "2026-09-01T00:00:00Z", "2027-09-01T00:00:00Z", None),
    ("u_chen", "attending", "p_102", "2026-09-01T00:00:00Z", "2027-09-01T00:00:00Z", None),
    ("u_rivera", "care_team", "p_101", "2026-09-15T00:00:00Z", "2026-09-22T00:00:00Z", None),
    ("u_okafor", "consultant", "p_101", "2026-09-17T00:00:00Z", "2026-09-27T00:00:00Z", None),
    ("u_okafor", "consultant", "p_102", "2026-08-01T00:00:00Z", "2026-08-15T00:00:00Z", None),
    ("u_diego", "caregiver", "p_103", "2026-06-01T00:00:00Z", "2026-12-01T00:00:00Z", "u_maria"),
    ("u_diego", "caregiver_notes", "p_103", "2026-03-01T00:00:00Z", "2026-06-01T00:00:00Z", "u_maria"),
    # Guardianship: a registration act (proof of guardianship at admissions), expiry = majority.
    ("u_haller", "guardian", "p_104", "2026-01-01T00:00:00Z", "2030-05-03T00:00:00Z", None),
]


def ts(y: int, m: int, d: int, hh: int = 9, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


ENCOUNTERS: list[dict[str, Any]] = [
    # p_101: two ambulatory follow-ups and the current inpatient stay on ward w_3b
    dict(
        key="p101-amb-2026-03-12",
        patient="p_101",
        status="finished",
        cls="AMB",
        type=("185349003", "Encounter for check up"),
        start=ts(2026, 3, 12),
        end=ts(2026, 3, 12, 9, 40),
        reason=("44054006", "Type 2 diabetes mellitus"),
        dept="internal-medicine",
    ),
    dict(
        key="p101-amb-2026-06-15",
        patient="p_101",
        status="finished",
        cls="AMB",
        type=("185349003", "Encounter for check up"),
        start=ts(2026, 6, 15),
        end=ts(2026, 6, 15, 9, 30),
        reason=("44054006", "Type 2 diabetes mellitus"),
        dept="internal-medicine",
    ),
    dict(
        key="p101-imp-2026-09-10",
        patient="p_101",
        status="in-progress",
        cls="IMP",
        type=("32485007", "Hospital admission"),
        start=ts(2026, 9, 10, 14, 20),
        end=None,
        reason=("433144002", "Chronic kidney disease stage 3"),
        dept="w_3b",
    ),
    # p_102
    dict(
        key="p102-amb-2026-07-01",
        patient="p_102",
        status="finished",
        cls="AMB",
        type=("185349003", "Encounter for check up"),
        start=ts(2026, 7, 1, 10),
        end=ts(2026, 7, 1, 10, 25),
        reason=("195967001", "Asthma"),
        dept="pulmonology",
    ),
    # p_103: last cardiology visit and the next booked appointment
    dict(
        key="p103-amb-2026-05-20",
        patient="p_103",
        status="finished",
        cls="AMB",
        type=("185349003", "Encounter for check up"),
        start=ts(2026, 5, 20, 11),
        end=ts(2026, 5, 20, 11, 30),
        reason=("38341003", "Hypertensive disorder"),
        dept="cardiology",
    ),
    # Next cardiology slot is clinical.appointments (Appointment/p103-cardio-2026-10-02),
    # not a planned-encounter stand-in.
    # p_205: emergency visit, no one holds a grant
    dict(
        key="p205-emer-2026-09-17",
        patient="p_205",
        status="finished",
        cls="EMER",
        type=("50849002", "Emergency room admission"),
        start=ts(2026, 9, 17, 22, 5),
        end=ts(2026, 9, 18, 2, 40),
        reason=("233604007", "Pneumonia"),
        dept="emergency",
    ),
    # p_104 (Lea, 14): a paediatric asthma review her guardian sees, and a confidential
    # adolescent-clinic visit labelled R + SEX that the guardian gets redacted.
    dict(
        key="p104-amb-2026-06-20",
        patient="p_104",
        status="finished",
        cls="AMB",
        type=("185349003", "Encounter for check up"),
        start=ts(2026, 6, 20, 15),
        end=ts(2026, 6, 20, 15, 30),
        reason=("195967001", "Asthma"),
        dept="pediatrics",
    ),
    dict(
        key="p104-amb-2026-08-14",
        patient="p_104",
        status="finished",
        cls="AMB",
        type=("185349003", "Encounter for check up"),
        start=ts(2026, 8, 14, 16),
        end=ts(2026, 8, 14, 16, 40),
        reason=("171057006", "Pregnancy prevention education"),
        dept="adolescent-medicine",
        conf="R",
        sens=["SEX"],
    ),
]

CONDITIONS: list[dict[str, Any]] = [
    dict(
        key="p101-t2dm",
        patient="p_101",
        enc="p101-amb-2026-03-12",
        code=("44054006", "Type 2 diabetes mellitus"),
        status="active",
        onset=date(2018, 4, 2),
        category="problem-list-item",
    ),
    dict(
        key="p101-ckd3",
        patient="p_101",
        enc="p101-imp-2026-09-10",
        code=("433144002", "Chronic kidney disease stage 3"),
        status="active",
        onset=date(2024, 11, 20),
        category="problem-list-item",
    ),
    dict(
        key="p101-htn",
        patient="p_101",
        enc=None,
        code=("38341003", "Hypertensive disorder"),
        status="active",
        onset=date(2015, 2, 10),
        category="problem-list-item",
    ),
    dict(
        key="p101-mdd",
        patient="p_101",
        enc=None,
        code=("35489007", "Depressive disorder"),
        status="active",
        onset=date(2023, 5, 8),
        category="problem-list-item",
        conf="V",
        sens=["PSY"],
    ),
    dict(
        key="p102-asthma",
        patient="p_102",
        enc="p102-amb-2026-07-01",
        code=("195967001", "Asthma"),
        status="active",
        onset=date(2009, 9, 1),
        category="problem-list-item",
    ),
    dict(
        key="p103-htn",
        patient="p_103",
        enc="p103-amb-2026-05-20",
        code=("38341003", "Hypertensive disorder"),
        status="active",
        onset=date(2019, 3, 4),
        category="problem-list-item",
    ),
    dict(
        key="p103-hld",
        patient="p_103",
        enc="p103-amb-2026-05-20",
        code=("55822004", "Hyperlipidemia"),
        status="active",
        onset=date(2021, 7, 19),
        category="problem-list-item",
    ),
    dict(
        key="p205-pneumonia",
        patient="p_205",
        enc="p205-emer-2026-09-17",
        code=("233604007", "Pneumonia"),
        status="active",
        onset=date(2026, 9, 17),
        category="encounter-diagnosis",
    ),
    # p_104: asthma the guardian sees; the adolescent-clinic health concern is R + SEX.
    dict(
        key="p104-asthma",
        patient="p_104",
        enc="p104-amb-2026-06-20",
        code=("195967001", "Asthma"),
        status="active",
        onset=date(2018, 3, 11),
        category="problem-list-item",
    ),
    dict(
        key="p104-contraception",
        patient="p_104",
        enc="p104-amb-2026-08-14",
        code=("171057006", "Pregnancy prevention education"),
        status="active",
        onset=date(2026, 8, 14),
        category="health-concern",
        conf="R",
        sens=["SEX"],
    ),
]

# Lab trend for p_101 across the three encounters; the latest values are abnormal.
LAB_SERIES: list[dict[str, Any]] = [
    dict(
        code=("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood"),
        unit="%",
        ref=(4.0, 5.6),
        values=[(ts(2026, 3, 12, 8), 8.4, "H"), (ts(2026, 6, 15, 8), 7.9, "H"), (ts(2026, 9, 11, 7), 7.2, "H")],
    ),
    dict(
        code=("2160-0", "Creatinine [Mass/volume] in Serum or Plasma"),
        unit="mg/dL",
        ref=(0.6, 1.1),
        values=[(ts(2026, 3, 12, 8), 1.1, "N"), (ts(2026, 6, 15, 8), 1.3, "H"), (ts(2026, 9, 11, 7), 1.5, "H")],
    ),
    dict(
        code=("2823-3", "Potassium [Moles/volume] in Serum or Plasma"),
        unit="mmol/L",
        ref=(3.5, 5.1),
        values=[(ts(2026, 3, 12, 8), 4.4, "N"), (ts(2026, 6, 15, 8), 4.9, "N"), (ts(2026, 9, 11, 7), 5.3, "H")],
    ),
    dict(
        code=("33914-3", "Glomerular filtration rate/1.73 sq M.predicted"),
        unit="mL/min/{1.73_m2}",
        ref=(60.0, None),
        values=[(ts(2026, 3, 12, 8), 62.0, "N"), (ts(2026, 6, 15, 8), 55.0, "L"), (ts(2026, 9, 11, 7), 48.0, "L")],
    ),
]
LAB_ENCOUNTER_BY_DATE = {
    date(2026, 3, 12): "p101-amb-2026-03-12",
    date(2026, 6, 15): "p101-amb-2026-06-15",
    date(2026, 9, 11): "p101-imp-2026-09-10",
}

OTHER_OBSERVATIONS: list[dict[str, Any]] = [
    dict(
        key="p103-chol-2026-05-20",
        patient="p_103",
        enc="p103-amb-2026-05-20",
        category="laboratory",
        code=("2093-3", "Cholesterol [Moles/volume] in Serum or Plasma"),
        at=ts(2026, 5, 20, 10),
        value=5.4,
        unit="mmol/L",
        ref=(None, 5.2),
        interp="H",
    ),
    dict(
        key="p205-wbc-2026-09-17",
        patient="p_205",
        enc="p205-emer-2026-09-17",
        category="laboratory",
        code=("6690-2", "Leukocytes [#/volume] in Blood by Automated count"),
        at=ts(2026, 9, 17, 22, 40),
        value=14.2,
        unit="10*3/uL",
        ref=(4.0, 10.5),
        interp="H",
    ),
    # p_104: routine paediatric labs, both normal.
    dict(
        key="p104-hb-2026-06-20",
        patient="p_104",
        enc="p104-amb-2026-06-20",
        category="laboratory",
        code=("718-7", "Hemoglobin [Mass/volume] in Blood"),
        at=ts(2026, 6, 20, 15, 10),
        value=13.1,
        unit="g/dL",
        ref=(12.0, 15.5),
        interp="N",
    ),
    dict(
        key="p104-eos-2026-06-20",
        patient="p_104",
        enc="p104-amb-2026-06-20",
        category="laboratory",
        code=("26449-9", "Eosinophils [#/volume] in Blood"),
        at=ts(2026, 6, 20, 15, 10),
        value=0.3,
        unit="10*3/uL",
        ref=(0.0, 0.5),
        interp="N",
    ),
]

# Blood-pressure panels: parent row + two component rows (component_of in /tools/query).
BP_PANELS: list[dict[str, Any]] = [
    dict(
        key="p101-bp-2026-09-11", patient="p_101", enc="p101-imp-2026-09-10", at=ts(2026, 9, 11, 7, 5), sys=148, dia=92
    ),
    dict(
        key="p103-bp-2026-05-20", patient="p_103", enc="p103-amb-2026-05-20", at=ts(2026, 5, 20, 11, 5), sys=138, dia=86
    ),
]

MEDICATIONS: list[dict[str, Any]] = [
    # p_101: the medication change is lisinopril stopped on admission, amlodipine started.
    dict(
        key="p101-metformin",
        patient="p_101",
        enc="p101-amb-2026-03-12",
        status="active",
        code=("860975", "metformin hydrochloride 500 MG Oral Tablet"),
        authored=ts(2018, 4, 2),
        dosage="500 mg by mouth twice daily with meals",
        freq=2,
        period=1,
        unit="d",
        dose=(500, "mg"),
        reason="p101-t2dm",
    ),
    dict(
        key="p101-lisinopril",
        patient="p_101",
        enc=None,
        status="stopped",
        code=("314076", "lisinopril 10 MG Oral Tablet"),
        authored=ts(2015, 2, 10),
        dosage="10 mg by mouth once daily",
        freq=1,
        period=1,
        unit="d",
        dose=(10, "mg"),
        reason="p101-htn",
    ),
    dict(
        key="p101-amlodipine",
        patient="p_101",
        enc="p101-imp-2026-09-10",
        status="active",
        code=("197361", "amlodipine 5 MG Oral Tablet"),
        authored=ts(2026, 9, 11, 9, 15),
        dosage="5 mg by mouth once daily",
        freq=1,
        period=1,
        unit="d",
        dose=(5, "mg"),
        reason="p101-htn",
    ),
    dict(
        key="p101-sertraline",
        patient="p_101",
        enc=None,
        status="active",
        code=("312940", "sertraline 50 MG Oral Tablet"),
        authored=ts(2023, 5, 8),
        dosage="50 mg by mouth once daily",
        freq=1,
        period=1,
        unit="d",
        dose=(50, "mg"),
        reason="p101-mdd",
        conf="R",
        sens=["PSY"],
    ),
    # p_102
    dict(
        key="p102-albuterol",
        patient="p_102",
        enc="p102-amb-2026-07-01",
        status="active",
        code=("745752", "albuterol 0.09 MG/ACTUAT Metered Dose Inhaler"),
        authored=ts(2026, 7, 1, 10, 20),
        dosage="2 puffs every 4 to 6 hours as needed",
        freq=None,
        period=None,
        unit=None,
        dose=None,
        reason="p102-asthma",
        as_needed=True,
    ),
    # p_103
    dict(
        key="p103-amlodipine",
        patient="p_103",
        enc="p103-amb-2026-05-20",
        status="active",
        code=("197361", "amlodipine 5 MG Oral Tablet"),
        authored=ts(2019, 3, 4),
        dosage="5 mg by mouth once daily",
        freq=1,
        period=1,
        unit="d",
        dose=(5, "mg"),
        reason="p103-htn",
    ),
    dict(
        key="p103-atorvastatin",
        patient="p_103",
        enc="p103-amb-2026-05-20",
        status="active",
        code=("617312", "atorvastatin 20 MG Oral Tablet"),
        authored=ts(2021, 7, 19),
        dosage="20 mg by mouth once daily at bedtime",
        freq=1,
        period=1,
        unit="d",
        dose=(20, "mg"),
        reason="p103-hld",
    ),
    # p_205
    dict(
        key="p205-amoxicillin",
        patient="p_205",
        enc="p205-emer-2026-09-17",
        status="active",
        code=("308182", "amoxicillin 500 MG Oral Capsule"),
        authored=ts(2026, 9, 18, 1, 30),
        dosage="500 mg by mouth three times daily for 7 days",
        freq=3,
        period=1,
        unit="d",
        dose=(500, "mg"),
        reason="p205-pneumonia",
    ),
    # p_104: the inhaler her guardian sees, and the adolescent-clinic prescription (R + SEX).
    dict(
        key="p104-albuterol",
        patient="p_104",
        enc="p104-amb-2026-06-20",
        status="active",
        code=("745752", "albuterol 0.09 MG/ACTUAT Metered Dose Inhaler"),
        authored=ts(2026, 6, 20, 15, 25),
        dosage="2 puffs every 4 to 6 hours as needed",
        freq=None,
        period=None,
        unit=None,
        dose=None,
        reason="p104-asthma",
        as_needed=True,
    ),
    dict(
        key="p104-contraceptive",
        patient="p_104",
        enc="p104-amb-2026-08-14",
        status="active",
        code=("748962", "levonorgestrel 0.15 MG / ethinyl estradiol 0.03 MG Oral Tablet"),
        authored=ts(2026, 8, 14, 16, 30),
        dosage="1 tablet by mouth once daily",
        freq=1,
        period=1,
        unit="d",
        dose=(1, "{tbl}"),
        reason="p104-contraception",
        conf="R",
        sens=["SEX"],
    ),
]

ALLERGIES: list[dict[str, Any]] = [
    dict(
        key="p101-peanut",
        patient="p_101",
        status="active",
        verification="confirmed",
        type="allergy",
        category=["food"],
        criticality="high",
        code=("91935009", "Allergy to peanut"),
        reaction=("39579001", "Anaphylaxis"),
        severity="severe",
        recorded=date(2010, 6, 1),
        onset=date(2010, 5, 28),
    ),
    dict(
        key="p101-penicillin",
        patient="p_101",
        status="active",
        verification="confirmed",
        type="allergy",
        category=["medication"],
        criticality="low",
        code=("91936005", "Allergy to penicillin"),
        reaction=("271807003", "Eruption of skin"),
        severity="mild",
        recorded=date(2012, 2, 14),
        onset=None,
    ),
]

DIET_ORDERS: list[dict[str, Any]] = [
    dict(
        key="p101-diet-2026-09-10",
        patient="p_101",
        enc="p101-imp-2026-09-10",
        status="active",
        intent="order",
        at=ts(2026, 9, 10, 16),
        diet_codes=["160670007", "386619000"],  # diabetic diet, low sodium diet (SNOMED CT)
        exclude=["256349002"],  # peanut (food) as a neutral excluded-food code
        allergy_keys=["p101-peanut"],
        ward="w_3b",
    ),
]

NOTES: list[dict[str, Any]] = [
    # Metadata only: text arrives with the notes pipeline. published stays false until then.
    dict(
        key="p101-psych-consult-2026-09-12",
        patient="p_101",
        enc="p101-imp-2026-09-10",
        type=("11488-4", "Consult note"),
        at=ts(2026, 9, 12, 15, 30),
        internal=True,
        provenance="clinical",
        conf="V",
        sens=["PSY"],
        text_key="p101-psych-consult-2026-09-12",
    ),
    dict(
        key="p101-admission-2026-09-10",
        patient="p_101",
        enc="p101-imp-2026-09-10",
        type=("18842-5", "Discharge summary"),
        at=ts(2026, 9, 10, 18),
        internal=False,
        provenance="clinical",
        conf="N",
        sens=[],
        text_key="p101-admission-2026-09-10",
    ),
    dict(
        key="p103-cardiology-2026-05-20",
        patient="p_103",
        enc="p103-amb-2026-05-20",
        type=("34117-2", "History and physical note"),
        at=ts(2026, 5, 20, 11, 40),
        internal=False,
        provenance="clinical",
        conf="N",
        sens=[],
        text_key="p103-cardiology-2026-05-20",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def sid(kind: str, key: str) -> str:
    return f"{SRC}/{kind}/{key}"


class Seeder:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.ids: dict[str, UUID] = {}  # "Encounter/key" -> uuid
        self.counts: dict[str, int] = {}

    def bump(self, table: str) -> None:
        self.counts[table] = self.counts.get(table, 0) + 1

    def upsert(self, table: str, source_key: str, cols: dict[str, Any], *, conflict: str = "source_id") -> UUID:
        names = list(cols)
        quoted = ", ".join(f'"{n}"' for n in names)
        placeholders = ", ".join(f"%({n})s" for n in names)
        updates = ", ".join(f'"{n}" = EXCLUDED."{n}"' for n in names if n not in (conflict, "patient_key"))
        sql = (
            f"INSERT INTO clinical.{table} ({quoted}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates} RETURNING id"
        )
        row = self.conn.execute(sql, cols).fetchone()
        assert row is not None
        self.ids[source_key] = row[0]
        self.bump(table)
        return row[0]

    def enc_id(self, key: str | None) -> UUID | None:
        return self.ids[f"Encounter/{key}"] if key else None

    # --- tables -----------------------------------------------------------

    def users(self) -> None:
        for user_id, role, dept, cred in USERS:
            self.conn.execute(
                "INSERT INTO identity.users (user_id, role, department, credential_level, active) "
                "VALUES (%s, %s, %s, %s, true) "
                "ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role, department = EXCLUDED.department, "
                "credential_level = EXCLUDED.credential_level, active = true",
                (user_id, role, dept, cred),
            )
            self.bump("identity.users")

    def patients(self) -> None:
        for key, sex, birth_year in PATIENTS:
            self.conn.execute(
                "INSERT INTO clinical.patients (patient_key, sex, birth_year, resource) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (patient_key) DO UPDATE SET sex = EXCLUDED.sex, birth_year = EXCLUDED.birth_year, "
                "resource = EXCLUDED.resource",
                (key, sex, birth_year, Jsonb({"resourceType": "Patient", "gender": sex, "birthDate": str(birth_year)})),
            )
            self.bump("patients")

    def encounters(self) -> None:
        for e in ENCOUNTERS:
            type_code, type_display = e["type"]
            reason_code, reason_display = e["reason"]
            resource = {
                "resourceType": "Encounter",
                "status": e["status"],
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": e["cls"]},
                "type": [{"coding": [{"system": SNOMED, "code": type_code, "display": type_display}]}],
                "period": {"start": e["start"].isoformat(), **({"end": e["end"].isoformat()} if e["end"] else {})},
                "reasonCode": [{"coding": [{"system": SNOMED, "code": reason_code, "display": reason_display}]}],
            }
            self.upsert(
                "encounters",
                f"Encounter/{e['key']}",
                dict(
                    source_id=sid("Encounter", e["key"]),
                    patient_key=e["patient"],
                    status=e["status"],
                    **{"class": e["cls"]},
                    type_code=type_code,
                    type_system=SNOMED,
                    type_display=type_display,
                    started_at=e["start"],
                    ended_at=e["end"],
                    reason_code=reason_code,
                    reason_system=SNOMED,
                    reason_display=reason_display,
                    dept=e["dept"],
                    confidentiality=e.get("conf", "N"),
                    sensitivity=e.get("sens", []),
                    resource=Jsonb(resource),
                ),
            )

    def conditions(self) -> None:
        for c in CONDITIONS:
            code, display = c["code"]
            resource = {
                "resourceType": "Condition",
                "code": {"coding": [{"system": SNOMED, "code": code, "display": display}]},
                "clinicalStatus": {"coding": [{"code": c["status"]}]},
                "verificationStatus": {"coding": [{"code": "confirmed"}]},
                "category": [{"coding": [{"code": c["category"]}]}],
                "onsetDateTime": c["onset"].isoformat(),
            }
            self.upsert(
                "conditions",
                f"Condition/{c['key']}",
                dict(
                    source_id=sid("Condition", c["key"]),
                    patient_key=c["patient"],
                    encounter_id=self.enc_id(c["enc"]),
                    code=code,
                    code_system=SNOMED,
                    display=display,
                    clinical_status=c["status"],
                    verification_status="confirmed",
                    category=c["category"],
                    onset_date=c["onset"],
                    recorded_date=c["onset"],
                    confidentiality=c.get("conf", "N"),
                    sensitivity=c.get("sens", []),
                    resource=Jsonb(resource),
                ),
            )

    def _observation(
        self,
        key: str,
        patient: str,
        enc: str | None,
        *,
        category: str | None,
        code: tuple[str, str],
        at: datetime,
        value: float | None,
        unit: str | None,
        ref: tuple[float | None, float | None] | None,
        interp: str | None,
        parent_id: UUID | None = None,
    ) -> UUID:
        code_value, display = code
        resource: dict[str, Any] = {
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{"system": LOINC, "code": code_value, "display": display}]},
            "effectiveDateTime": at.isoformat(),
        }
        if category:
            resource["category"] = [{"coding": [{"code": category}]}]
        if value is not None:
            resource["valueQuantity"] = {"value": value, "unit": unit, "system": UCUM, "code": unit}
        if interp:
            resource["interpretation"] = [{"coding": [{"code": interp}]}]
        ref_low, ref_high = ref if ref else (None, None)
        return self.upsert(
            "observations",
            f"Observation/{key}",
            dict(
                source_id=sid("Observation", key),
                patient_key=patient,
                encounter_id=self.enc_id(enc),
                parent_id=parent_id,
                status="final",
                category=category,
                code=code_value,
                code_system=LOINC,
                display=display,
                effective_at=at,
                issued_at=at,
                value_num=value,
                unit=unit if value is not None else None,
                interpretation=interp,
                ref_low=ref_low,
                ref_high=ref_high,
                confidentiality="N",
                sensitivity=[],
                resource=Jsonb(resource),
            ),
        )

    def observations(self) -> None:
        for series in LAB_SERIES:
            code_value, _ = series["code"]
            for at, value, interp in series["values"]:
                key = f"p101-{code_value}-{at.date().isoformat()}"
                self._observation(
                    key,
                    "p_101",
                    LAB_ENCOUNTER_BY_DATE[at.date()],
                    category="laboratory",
                    code=series["code"],
                    at=at,
                    value=value,
                    unit=series["unit"],
                    ref=series["ref"],
                    interp=interp,
                )
        for o in OTHER_OBSERVATIONS:
            self._observation(
                o["key"],
                o["patient"],
                o["enc"],
                category=o["category"],
                code=o["code"],
                at=o["at"],
                value=o["value"],
                unit=o["unit"],
                ref=o["ref"],
                interp=o["interp"],
            )
        for bp in BP_PANELS:
            parent = self._observation(
                bp["key"],
                bp["patient"],
                bp["enc"],
                category="vital-signs",
                code=("85354-9", "Blood pressure panel with all children optional"),
                at=bp["at"],
                value=None,
                unit=None,
                ref=None,
                interp=None,
            )
            self._observation(
                f"{bp['key']}#8480-6",
                bp["patient"],
                bp["enc"],
                category="vital-signs",
                code=("8480-6", "Systolic blood pressure"),
                at=bp["at"],
                value=bp["sys"],
                unit="mm[Hg]",
                ref=(90.0, 140.0),
                interp="H" if bp["sys"] >= 140 else "N",
                parent_id=parent,
            )
            self._observation(
                f"{bp['key']}#8462-4",
                bp["patient"],
                bp["enc"],
                category="vital-signs",
                code=("8462-4", "Diastolic blood pressure"),
                at=bp["at"],
                value=bp["dia"],
                unit="mm[Hg]",
                ref=(60.0, 90.0),
                interp="H" if bp["dia"] >= 90 else "N",
                parent_id=parent,
            )

    def medications(self) -> None:
        for m in MEDICATIONS:
            code, display = m["code"]
            dose = m.get("dose")
            resource: dict[str, Any] = {
                "resourceType": "MedicationRequest",
                "status": m["status"],
                "intent": "order",
                "medicationCodeableConcept": {"coding": [{"system": RXNORM, "code": code, "display": display}]},
                "authoredOn": m["authored"].isoformat(),
                "dosageInstruction": [{"text": m["dosage"]}],
            }
            self.upsert(
                "medications",
                f"MedicationRequest/{m['key']}",
                dict(
                    source_id=sid("MedicationRequest", m["key"]),
                    patient_key=m["patient"],
                    encounter_id=self.enc_id(m["enc"]),
                    status=m["status"],
                    intent="order",
                    code=code,
                    code_system=RXNORM,
                    display=display,
                    authored_at=m["authored"],
                    dosage_text=m["dosage"],
                    timing_frequency=m.get("freq"),
                    timing_period=m.get("period"),
                    timing_period_unit=m.get("unit"),
                    dose_value=dose[0] if dose else None,
                    dose_unit=dose[1] if dose else None,
                    as_needed=m.get("as_needed"),
                    reason_condition_id=self.ids.get(f"Condition/{m['reason']}") if m.get("reason") else None,
                    confidentiality=m.get("conf", "N"),
                    sensitivity=m.get("sens", []),
                    resource=Jsonb(resource),
                ),
            )

    def allergies(self) -> None:
        for a in ALLERGIES:
            code, display = a["code"]
            reaction_code, reaction_display = a["reaction"]
            resource = {
                "resourceType": "AllergyIntolerance",
                "clinicalStatus": {"coding": [{"code": a["status"]}]},
                "verificationStatus": {"coding": [{"code": a["verification"]}]},
                "type": a["type"],
                "category": a["category"],
                "criticality": a["criticality"],
                "code": {"coding": [{"system": SNOMED, "code": code, "display": display}]},
                "reaction": [
                    {
                        "manifestation": [
                            {"coding": [{"system": SNOMED, "code": reaction_code, "display": reaction_display}]}
                        ],
                        "severity": a["severity"],
                    }
                ],
                "recordedDate": a["recorded"].isoformat(),
            }
            self.upsert(
                "allergies",
                f"AllergyIntolerance/{a['key']}",
                dict(
                    source_id=sid("AllergyIntolerance", a["key"]),
                    patient_key=a["patient"],
                    encounter_id=None,
                    clinical_status=a["status"],
                    verification_status=a["verification"],
                    type=a["type"],
                    category=a["category"],
                    criticality=a["criticality"],
                    code=code,
                    code_system=SNOMED,
                    display=display,
                    reaction_code=reaction_code,
                    reaction_system=SNOMED,
                    reaction_display=reaction_display,
                    severity=a["severity"],
                    recorded_date=a["recorded"],
                    onset_date=a["onset"],
                    confidentiality="N",
                    sensitivity=[],
                    resource=Jsonb(resource),
                ),
            )

    def diet_orders(self) -> None:
        for d in DIET_ORDERS:
            resource = {
                "resourceType": "NutritionOrder",
                "status": d["status"],
                "intent": d["intent"],
                "dateTime": d["at"].isoformat(),
                "oralDiet": {"type": [{"coding": [{"system": SNOMED, "code": c}]} for c in d["diet_codes"]]},
                "excludeFoodModifier": [{"coding": [{"system": SNOMED, "code": c}]} for c in d["exclude"]],
            }
            allergy_ids = [self.ids[f"AllergyIntolerance/{k}"] for k in d["allergy_keys"]]
            self.upsert(
                "diet_orders",
                f"NutritionOrder/{d['key']}",
                dict(
                    source_id=sid("NutritionOrder", d["key"]),
                    patient_key=d["patient"],
                    encounter_id=self.enc_id(d["enc"]),
                    status=d["status"],
                    intent=d["intent"],
                    ordered_at=d["at"],
                    diet_codes=d["diet_codes"],
                    exclude_food_modifiers=d["exclude"],
                    allergy_ids=allergy_ids,
                    ward=d["ward"],
                    confidentiality="N",
                    sensitivity=[],
                    resource=Jsonb(resource),
                ),
            )

    def imaging(self) -> None:
        study_id = self.upsert(
            "studies",
            "ImagingStudy/p101-cxr-2026-09-11",
            dict(
                source_id=sid("ImagingStudy", "p101-cxr-2026-09-11"),
                patient_key="p_101",
                encounter_id=self.enc_id("p101-imp-2026-09-10"),
                status="available",
                study_at=ts(2026, 9, 11, 9),
                modality="CR",
                procedure_code="36643-5",
                procedure_system=LOINC,
                procedure_display="Chest X-ray",
                confidentiality="N",
                sensitivity=[],
                resource=Jsonb({"resourceType": "ImagingStudy", "status": "available"}),
            ),
        )
        self.upsert(
            "diagnostic_reports",
            "DiagnosticReport/p101-cxr-2026-09-11",
            dict(
                source_id=sid("DiagnosticReport", "p101-cxr-2026-09-11"),
                patient_key="p_101",
                encounter_id=self.enc_id("p101-imp-2026-09-10"),
                status="final",
                category="RAD",
                code="36643-5",
                code_system=LOINC,
                display="Chest X-ray",
                effective_at=ts(2026, 9, 11, 9),
                issued_at=ts(2026, 9, 11, 10),
                conclusion_text="No acute cardiopulmonary process.",
                study_id=study_id,
                report_ref="reports/p_101/cxr.txt",
                confidentiality="N",
                sensitivity=[],
                resource=Jsonb({"resourceType": "DiagnosticReport", "status": "final", "category": "RAD"}),
            ),
        )

    def notes(self) -> None:
        for n in NOTES:
            type_code, type_display = n["type"]
            resource = {
                "resourceType": "DocumentReference",
                "status": "current",
                "type": {"coding": [{"system": LOINC, "code": type_code, "display": type_display}]},
                "category": [{"coding": [{"code": CLINICAL_NOTE}]}],
                "date": n["at"].isoformat(),
            }
            self.upsert(
                "notes",
                f"DocumentReference/{n['key']}",
                dict(
                    source_id=sid("DocumentReference", n["key"]),
                    patient_key=n["patient"],
                    encounter_id=self.enc_id(n["enc"]),
                    status="current",
                    type_code=type_code,
                    type_system=LOINC,
                    type_display=type_display,
                    category=CLINICAL_NOTE,
                    authored_at=n["at"],
                    internal=n["internal"],
                    provenance=n["provenance"],
                    published=False,
                    confidentiality=n["conf"],
                    sensitivity=n["sens"],
                    resource=Jsonb(resource),
                ),
            )

    def ensure_appointments_schema(self) -> None:
        sql_path = (
            Path(__file__).resolve().parents[1] / "deploy/patient360/sql/fhir/06-appointments.sql"
        )
        self.conn.execute(sql_path.read_text(encoding="utf-8"))

    def appointments(self) -> None:
        # Maria's next cardiology slot with Dr. Okafor (replaces the planned-encounter stand-in).
        self.upsert(
            "appointments",
            "Appointment/p103-cardio-2026-10-02",
            dict(
                source_id=sid("Appointment", "p103-cardio-2026-10-02"),
                patient_key="p_103",
                practitioner_user_id="u_okafor",
                status="booked",
                start_at=ts(2026, 10, 2, 9, 30),
                end_at=ts(2026, 10, 2, 10),
                dept="cardiology",
                service_type="185349003",
                service_type_system=SNOMED,
                service_type_display="Encounter for check up",
                created_by="u_maria",
                confidentiality="N",
                sensitivity=[],
                resource=Jsonb({"resourceType": "Appointment", "status": "booked"}),
            ),
        )


def vault_write(url: str, token: str, mount: str, path: str, data: dict[str, Any]) -> None:
    """KV v2 write of one linkage record. Needs the worker token (create/update on linkage/*)."""
    req = urllib.request.Request(
        f"{url.rstrip('/')}/v1/{mount.strip('/')}/data/linkage/{path}",
        data=json.dumps({"data": data}, ensure_ascii=False).encode("utf-8"),
        headers={"X-Vault-Token": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise SystemExit(f"vault write for linkage/{path.split('/')[0]} returned {resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise SystemExit(
                "vault refused the write (403): use the worker token (PATIENT360_LINKAGE_WORKER_TOKEN), "
                "the backend token is read-only"
            ) from exc
        raise SystemExit(f"vault write for linkage/{path.split('/')[0]} returned {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"vault unreachable at {url}: {exc.reason}") from exc


def write_vault_links(url: str, token: str, mount: str, links: dict[str, str]) -> int:
    for user_id, patient_key in links.items():
        vault_write(url, token, mount, f"self/{user_id}", {"patient_key": patient_key})
    return len(links)


def write_vault_identities(url: str, token: str, mount: str, identities: dict[str, dict[str, Any]]) -> int:
    """`register`: real identity <-> pseudonym, vault only. Never mirrored into Postgres."""
    for patient_key, record in identities.items():
        vault_write(url, token, mount, f"identity/{patient_key}", {"patient_key": patient_key, **record})
    return len(identities)


def write_seeded_consents(dsn: str) -> int:
    """One consent_granted row per demo grant tuple, detail.seeded = true. Idempotent by id."""
    written = 0
    with psycopg.connect(dsn, autocommit=True) as conn:
        for grantee, relation, patient, start, expiry, granted_by in DEMO_GRANTS:
            consent_id = uuid5(CONSENT_NAMESPACE, f"{grantee}|{relation}|{patient}")
            guardianship = relation == "guardian"
            detail = {
                "kind": "guardianship" if guardianship else "consent",
                "relation": relation,
                "grantee": grantee,
                "granted_by": granted_by,
                "basis": "self_match" if granted_by else ("registration" if guardianship else "seed"),
                "start": start,
                "expiry": expiry,
                "justification": "legal guardian; proof of guardianship on file at admissions"
                if guardianship
                else None,
                "tuple": {
                    "user": f"user:{grantee}",
                    "relation": relation,
                    "object": f"patient:{patient}",
                    "start": start,
                    "expiry": expiry,
                },
                "seeded": True,
                "source": "tuples.demo.yaml",
            }
            # The worker holds INSERT only (no SELECT), so ON CONFLICT is not available either:
            # a duplicate id is detected by the primary key and skipped. Each insert is its
            # own autocommit statement, so a rejected row leaves the chain untouched.
            try:
                conn.execute(
                    "INSERT INTO audit.audit_events (id, event_type, agent_user, agent_software, purpose_of_event, "
                    "entity_patient, entity_resource, outcome, outcome_desc, detail) "
                    "VALUES (%s, 'consent_granted', %s, 'seed_demo', %s, %s, %s, '0', 'seeded', %s)",
                    (
                        consent_id,
                        granted_by,
                        "PATRQT" if granted_by else "HOPERAT",
                        patient,
                        f"consent/{relation}/{grantee}",
                        Jsonb(detail),
                    ),
                )
            except psycopg.errors.UniqueViolation:
                continue
            written += 1
    return written


def write_ingest_audit(dsn: str, detail: dict[str, Any]) -> str:
    # Own connection, autocommit: the hash-chain trigger holds an advisory lock to commit.
    # The worker holds INSERT only (no SELECT), so RETURNING is not available: the id is
    # generated here and supplied explicitly.
    audit_id = uuid4()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO audit.audit_events (id, event_type, agent_user, agent_software, purpose_of_event, outcome, "
            "outcome_desc, detail) VALUES (%s, 'ingest', NULL, 'seed_demo', 'HOPERAT', '0', 'seed_demo', %s)",
            (audit_id, Jsonb(detail)),
        )
    return str(audit_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE, help="dotenv with PATIENT360_* values")
    ap.add_argument("--dsn", help="override: postgres://p360_worker:...@127.0.0.1:5432/fhir")
    ap.add_argument("--vault-url", help="override: http://127.0.0.1:8200")
    ap.add_argument("--vault-token", help="override: PATIENT360_LINKAGE_WORKER_TOKEN (falls back to the root token)")
    ap.add_argument("--vault-mount", default="secret")
    ap.add_argument("--skip-vault", action="store_true", help="write neither the self link nor the identities")
    args = ap.parse_args(argv)

    env = {**load_env_file(args.env_file), **os.environ}
    dsn = (
        args.dsn
        or env.get("PATIENT360_WORKER_DSN")
        or (
            f"postgres://p360_worker:{env.get('PATIENT360_WORKER_PASSWORD', 'patient360-worker-dev')}"
            f"@{env.get('PATIENT360_PG_HOST', '127.0.0.1')}:{env.get('PATIENT360_PG_PORT', '5432')}/fhir"
        )
    )
    vault_url = args.vault_url or env.get("PATIENT360_LINKAGE_URL", "http://127.0.0.1:8200")
    vault_token = (
        args.vault_token
        or env.get("PATIENT360_LINKAGE_WORKER_TOKEN")
        or env.get("PATIENT360_LINKAGE_TOKEN", "patient360-linkage-dev")
    )

    with psycopg.connect(dsn) as conn:
        seeder = Seeder(conn)
        with conn.transaction():
            seeder.users()
            seeder.patients()
            seeder.encounters()
            seeder.conditions()
            seeder.observations()
            seeder.medications()
            seeder.allergies()
            seeder.diet_orders()
            seeder.notes()
            seeder.imaging()
            seeder.ensure_appointments_schema()
            seeder.appointments()

    consents_written = write_seeded_consents(dsn)

    vault_written = 0
    identities_written = 0
    if not args.skip_vault:
        vault_written = write_vault_links(vault_url, vault_token, args.vault_mount, VAULT_LINKS)
        identities_written = write_vault_identities(vault_url, vault_token, args.vault_mount, IDENTITIES)

    detail = {
        "kind": "seed_demo",
        "source": SRC,
        "patients": [p[0] for p in PATIENTS],
        "counts": seeder.counts,
        "vault_links": vault_written,
        "vault_identities": identities_written,
        "seeded_consents": consents_written,
        "adversarial": [],
        "notes_published": 0,
    }
    audit_id = write_ingest_audit(dsn, detail)

    print(json.dumps({"ok": True, "audit_id": audit_id, **detail}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
