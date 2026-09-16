-- FHIR-flattened clinical tables only. Opaque patient_key; no grants, audit, vectors, or names.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE patients (
    patient_key text PRIMARY KEY,
    birth_year integer,
    sex text,
    resource jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE conditions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_key text NOT NULL REFERENCES patients (patient_key),
    code text,
    display text,
    onset_date date,
    resource jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_key text NOT NULL REFERENCES patients (patient_key),
    code text,
    display text,
    value_num double precision,
    value_text text,
    unit text,
    effective_at timestamptz,
    resource jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE studies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_key text NOT NULL REFERENCES patients (patient_key),
    modality text,
    orthanc_id text,
    description text,
    study_at timestamptz
);
