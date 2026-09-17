-- Patient360 `fhir` database: clinical base tables.
--
-- FHIR R4 (4.0.1) element projections, one table per resource type, keyed by
-- the opaque patient_key issued by the linkage vault. The source Patient.id
-- never enters this database. Contract: docs/Patient360-FHIR-Resource-Plan.md.
--
-- Conventions shared by every clinical table
--   id               surrogate uuid, internal joins only
--   cite_id          short random id shown to the agent and cited in answers
--   source_id        '{resourceType}/{id}' from the bundle; unique, drives idempotent upserts
--   patient_key      opaque p_xxx (never the source id, never an MRN)
--   encounter_id     resolved Encounter reference, nullable
--   confidentiality  HL7 v3 Confidentiality: N normal, R restricted, V very restricted
--   sensitivity      HL7 v3 ActCode sensitivity tags (PSY, ETH, HIV, STD, SEX, GDIS, SDV)
--   resource         projected JSONB; a CHECK rejects any key outside the element allowlist
--   code / code_system / display   one FHIR Coding; a code without its system is rejected
--   FHIR dateTime/instant -> timestamptz; elements reduced to date precision -> date
--
-- Patient boundary: every reference between clinical rows (encounter_id,
-- parent_id, reason_condition_id, study_id, report results) is a composite
-- foreign key that carries patient_key, so a row can only point at rows of the
-- same patient. Referenced tables expose UNIQUE (id, patient_key) for this.
-- ON DELETE SET NULL (column) needs PostgreSQL 15+.
--
-- Coded elements are checked against named value sets, `clinical.vs_*()` in
-- 00-roles-extensions.sql, each carrying its FHIR canonical URL and binding
-- strength. Elements FHIR makes mandatory (1..1) are NOT NULL.
--
-- Batch provenance (Synthea version, seeds, reference date, per-resource-type
-- ingested/skipped/quarantined counts, flagged adversarial notes) is recorded by
-- the worker as an `ingest` row in audit.audit_events (detail jsonb), not here.

--------------------------------------------------------------------------------
-- Patient
--------------------------------------------------------------------------------

CREATE TABLE clinical.patients (
    patient_key     text PRIMARY KEY CHECK (patient_key ~ '^p_[0-9a-z]+$'),
    sex             text CHECK (sex = ANY (clinical.vs_administrative_gender())),  -- Patient.gender
    birth_year      integer CHECK (birth_year BETWEEN 1900 AND 2100),             -- Patient.birthDate, year only
    deceased        boolean NOT NULL DEFAULT false,                                -- Patient.deceased[x]
    deceased_year   integer,
    confidentiality text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity     text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    -- Projected Patient. birthDate and deceasedDateTime are kept at year precision
    -- (FHIR date/dateTime allow YYYY), so the object stays valid FHIR without a full DOB.
    resource        jsonb NOT NULL DEFAULT '{}'
                    CHECK (jsonb_typeof(resource) = 'object'
                           AND (resource - ARRAY['resourceType', 'gender', 'birthDate', 'deceasedBoolean', 'deceasedDateTime']::text[]) = '{}'::jsonb
                           AND (resource->>'birthDate' IS NULL OR resource->>'birthDate' ~ '^\d{4}$')
                           AND (resource->>'deceasedDateTime' IS NULL OR resource->>'deceasedDateTime' ~ '^\d{4}$')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (deceased OR deceased_year IS NULL),
    CHECK (deceased_year IS NULL OR birth_year IS NULL OR deceased_year >= birth_year)
);

COMMENT ON TABLE clinical.patients IS 'Patient projection. No source_id: the source Patient.id and MRN exist only in the linkage vault. birth_year, sex, deceased_year are quasi-identifiers (see column_policy).';
COMMENT ON COLUMN clinical.patients.birth_year IS 'Quasi-identifier. Report ages >= 90 as 90+ via clinical.age_display().';

CREATE INDEX patients_sensitivity_idx ON clinical.patients USING gin (sensitivity);

CREATE TRIGGER patients_touch_updated_at
    BEFORE UPDATE ON clinical.patients
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- Encounter (created before Condition/Observation, which reference it)
--------------------------------------------------------------------------------

CREATE TABLE clinical.encounters (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id         text NOT NULL UNIQUE DEFAULT clinical.cite_id('enc'),
    source_id       text NOT NULL UNIQUE,
    patient_key     text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    status          text NOT NULL CHECK (status = ANY (clinical.vs_encounter_status())),
    class           text NOT NULL CHECK (class = ANY (clinical.vs_encounter_class())),      -- v3-ActEncounterCode
    type_code       text,                                                                  -- Encounter.type[0].coding (SNOMED)
    type_system     text,
    type_display    text,
    started_at      timestamptz,                                                           -- Encounter.period.start
    ended_at        timestamptz,                                                           -- Encounter.period.end
    reason_code     text,                                                                  -- Encounter.reasonCode[0].coding
    reason_system   text,
    reason_display  text,
    dept            text,                                                                  -- static mapping of serviceProvider; never the provider itself
    confidentiality text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity     text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource        jsonb NOT NULL DEFAULT '{}'
                    CHECK (jsonb_typeof(resource) = 'object'
                           AND (resource - ARRAY['resourceType', 'status', 'class', 'type', 'period', 'reasonCode']::text[]) = '{}'::jsonb),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, patient_key),                                                              -- target for composite FKs
    CHECK ((type_code IS NULL) = (type_system IS NULL)),
    CHECK ((reason_code IS NULL) = (reason_system IS NULL)),
    CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at)
);

COMMENT ON TABLE clinical.encounters IS 'Encounter projection. participant, serviceProvider, location, hospitalization, identifier are dropped; dept is a static department tag.';

CREATE INDEX encounters_patient_started_idx ON clinical.encounters (patient_key, started_at DESC);
CREATE INDEX encounters_sensitivity_idx     ON clinical.encounters USING gin (sensitivity);

CREATE TRIGGER encounters_touch_updated_at
    BEFORE UPDATE ON clinical.encounters
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- Condition
--------------------------------------------------------------------------------

CREATE TABLE clinical.conditions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id             text NOT NULL UNIQUE DEFAULT clinical.cite_id('cond'),
    source_id           text NOT NULL UNIQUE,
    patient_key         text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id        uuid,
    code                text,                                                              -- Condition.code.coding (SNOMED); 0..1 in R4 core
    code_system         text,
    display             text,
    clinical_status     text CHECK (clinical_status = ANY (clinical.vs_condition_clinical_status())),
    verification_status text CHECK (verification_status = ANY (clinical.vs_condition_verification_status())),
    category            text CHECK (category = ANY (clinical.vs_condition_category())),
    onset_date          date,                                                              -- Condition.onsetDateTime, date precision
    abatement_date      date,                                                              -- Condition.abatementDateTime
    recorded_date       date,                                                              -- Condition.recordedDate
    confidentiality     text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity         text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource            jsonb NOT NULL DEFAULT '{}'
                        CHECK (jsonb_typeof(resource) = 'object'
                               AND (resource - ARRAY['resourceType', 'code', 'clinicalStatus', 'verificationStatus', 'category',
                                                     'onsetDateTime', 'abatementDateTime', 'recordedDate']::text[]) = '{}'::jsonb),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, patient_key),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    CHECK ((code IS NULL) = (code_system IS NULL)),
    CHECK (abatement_date IS NULL OR onset_date IS NULL OR abatement_date >= onset_date)
);

COMMENT ON TABLE clinical.conditions IS 'Condition projection. Labels come from SNOMED code lists and clinical.concept_closure (mental disorder -> R+PSY, HIV -> V+HIV, ...). asserter, recorder, evidence, note, stage, identifier are dropped.';

CREATE INDEX conditions_patient_code_idx  ON clinical.conditions (patient_key, code);
CREATE INDEX conditions_patient_onset_idx ON clinical.conditions (patient_key, onset_date DESC);
CREATE INDEX conditions_encounter_idx     ON clinical.conditions (encounter_id);
CREATE INDEX conditions_sensitivity_idx   ON clinical.conditions USING gin (sensitivity);

CREATE TRIGGER conditions_touch_updated_at
    BEFORE UPDATE ON clinical.conditions
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- Observation (components flatten to child rows via parent_id)
--------------------------------------------------------------------------------

CREATE TABLE clinical.observations (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id           text NOT NULL UNIQUE DEFAULT clinical.cite_id('obs'),
    source_id         text NOT NULL UNIQUE,                                                -- 'Observation/{id}' or 'Observation/{id}#{componentCode}'
    patient_key       text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id      uuid,
    parent_id         uuid,                                                                -- set on Observation.component rows
    status            text NOT NULL CHECK (status = ANY (clinical.vs_observation_status())),
    category          text CHECK (category = ANY (clinical.vs_observation_category())),      -- R4 core + US Core 6.1
    code              text NOT NULL,                                                       -- Observation.code.coding (LOINC) or component.code; 1..1
    code_system       text,
    display           text,
    effective_at      timestamptz,                                                         -- effectiveDateTime / effectivePeriod.start
    issued_at         timestamptz,                                                         -- Observation.issued
    value_num         numeric,                                                             -- valueQuantity.value / valueInteger
    unit              text,                                                                -- valueQuantity.code (UCUM)
    value_code        text,                                                                -- valueCodeableConcept.coding[0]
    value_code_system text,
    value_display     text,
    value_text        text,                                                                -- valueString
    value_bool        boolean,                                                             -- valueBoolean
    interpretation    text,                                                                -- interpretation[0].coding.code, v3-ObservationInterpretation
    ref_low           numeric,                                                             -- referenceRange[0].low.value
    ref_high          numeric,                                                             -- referenceRange[0].high.value
    ref_text          text,                                                                -- referenceRange[0].text
    confidentiality   text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity       text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource          jsonb NOT NULL DEFAULT '{}'
                      CHECK (jsonb_typeof(resource) = 'object'
                             AND (resource - ARRAY['resourceType', 'status', 'category', 'code', 'effectiveDateTime', 'effectivePeriod',
                                                   'issued', 'valueQuantity', 'valueCodeableConcept', 'valueString', 'valueBoolean',
                                                   'valueInteger', 'component', 'interpretation', 'referenceRange']::text[]) = '{}'::jsonb),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, patient_key),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    FOREIGN KEY (parent_id, patient_key) REFERENCES clinical.observations (id, patient_key)
        ON DELETE CASCADE,
    CHECK ((code IS NULL) = (code_system IS NULL)),
    CHECK ((value_code IS NULL) = (value_code_system IS NULL)),
    -- Observation.value[x] is a choice type: at most one value column is set.
    CHECK (num_nonnulls(value_num, value_code, value_text, value_bool) <= 1),
    CHECK (unit IS NULL OR value_num IS NOT NULL),
    CHECK (ref_low IS NULL OR ref_high IS NULL OR ref_high >= ref_low),
    CHECK (parent_id IS NULL OR parent_id <> id)
);

COMMENT ON TABLE clinical.observations IS 'Observation projection. Component observations (blood pressure, panels) are child rows with parent_id and their own code. performer, device, specimen, note, identifier are dropped.';
COMMENT ON COLUMN clinical.observations.unit IS 'UCUM code from valueQuantity.code (fallback valueQuantity.unit).';

CREATE INDEX observations_patient_effective_idx ON clinical.observations (patient_key, effective_at DESC);
CREATE INDEX observations_patient_code_idx      ON clinical.observations (patient_key, code);
CREATE INDEX observations_patient_category_idx  ON clinical.observations (patient_key, category);
CREATE INDEX observations_encounter_idx         ON clinical.observations (encounter_id);
CREATE INDEX observations_parent_idx            ON clinical.observations (parent_id);
CREATE INDEX observations_sensitivity_idx       ON clinical.observations USING gin (sensitivity);

CREATE TRIGGER observations_touch_updated_at
    BEFORE UPDATE ON clinical.observations
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- ImagingStudy (metadata tier; pixels live in Orthanc behind the media proxy)
--------------------------------------------------------------------------------

CREATE TABLE clinical.studies (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id            text NOT NULL UNIQUE DEFAULT clinical.cite_id('img'),
    source_id          text NOT NULL UNIQUE,
    patient_key        text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id       uuid,
    status             text NOT NULL CHECK (status = ANY (clinical.vs_imaging_study_status())),
    study_at           timestamptz,                                                        -- ImagingStudy.started
    modality           text,                                                               -- modality[0].code, DICOM CID 29 (CT, MR, US, CR, DX, ...)
    description        text,                                                               -- ImagingStudy.description
    series_count       integer CHECK (series_count IS NULL OR series_count >= 0),          -- numberOfSeries
    instance_count     integer CHECK (instance_count IS NULL OR instance_count >= 0),      -- numberOfInstances
    procedure_code     text,                                                               -- procedureCode[0].coding
    procedure_system   text,
    procedure_display  text,
    body_site_code     text,                                                               -- series[0].bodySite (SNOMED)
    body_site_system   text,
    body_site_display  text,
    orthanc_id         text,                                                               -- Orthanc study id when pixels are loaded; never a DICOM UID
    confidentiality    text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity        text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource           jsonb NOT NULL DEFAULT '{}'
                       CHECK (jsonb_typeof(resource) = 'object'
                              AND (resource - ARRAY['resourceType', 'status', 'started', 'modality', 'description', 'numberOfSeries',
                                                    'numberOfInstances', 'procedureCode', 'bodySite']::text[]) = '{}'::jsonb),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, patient_key),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    CHECK ((procedure_code IS NULL) = (procedure_system IS NULL)),
    CHECK ((body_site_code IS NULL) = (body_site_system IS NULL))
);

COMMENT ON TABLE clinical.studies IS 'ImagingStudy projection. series/instance UIDs, referrer, interpreter, endpoint, identifier are dropped. Pixels are never a tool output.';

CREATE INDEX studies_patient_study_at_idx ON clinical.studies (patient_key, study_at DESC);
CREATE INDEX studies_encounter_idx        ON clinical.studies (encounter_id);
CREATE INDEX studies_sensitivity_idx      ON clinical.studies USING gin (sensitivity);

CREATE TRIGGER studies_touch_updated_at
    BEFORE UPDATE ON clinical.studies
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();
