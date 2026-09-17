-- Patient360 `fhir` database: remaining clinical tables, terminology closure,
-- column policy. Conventions are documented at the top of 01-init.sql.

--------------------------------------------------------------------------------
-- MedicationRequest (+ resolved Medication.code)
--------------------------------------------------------------------------------

CREATE TABLE clinical.medications (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id             text NOT NULL UNIQUE DEFAULT clinical.cite_id('med'),
    source_id           text NOT NULL UNIQUE,
    patient_key         text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id        uuid,
    status              text NOT NULL CHECK (status = ANY (clinical.vs_medication_request_status())),
    intent              text NOT NULL CHECK (intent = ANY (clinical.vs_medication_request_intent())),
    code                text NOT NULL,                                                     -- medicationCodeableConcept.coding (RxNorm); medication[x] is 1..1
    code_system         text,
    display             text,
    authored_at         timestamptz,                                                       -- MedicationRequest.authoredOn
    dosage_text         text,                                                              -- dosageInstruction[0].text
    timing_frequency    integer CHECK (timing_frequency IS NULL OR timing_frequency > 0),  -- dosageInstruction[0].timing.repeat.frequency
    timing_period       numeric CHECK (timing_period IS NULL OR timing_period > 0),        -- .timing.repeat.period
    timing_period_unit  text CHECK (timing_period_unit = ANY (clinical.vs_units_of_time())),  -- .timing.repeat.periodUnit
    dose_value          numeric,                                                           -- .doseAndRate[0].doseQuantity.value
    dose_unit           text,                                                              -- .doseAndRate[0].doseQuantity.code (UCUM)
    as_needed           boolean,                                                           -- .asNeededBoolean
    reason_condition_id uuid,                                                              -- reasonReference[0] -> Condition
    confidentiality     text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity         text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource            jsonb NOT NULL DEFAULT '{}'
                        CHECK (jsonb_typeof(resource) = 'object'
                               AND (resource - ARRAY['resourceType', 'status', 'intent', 'medicationCodeableConcept', 'authoredOn',
                                                     'dosageInstruction', 'reasonReference']::text[]) = '{}'::jsonb),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    FOREIGN KEY (reason_condition_id, patient_key) REFERENCES clinical.conditions (id, patient_key)
        ON DELETE SET NULL (reason_condition_id),
    CHECK ((code IS NULL) = (code_system IS NULL)),
    CHECK ((timing_period IS NULL) = (timing_period_unit IS NULL)),
    CHECK ((dose_value IS NULL) OR (dose_unit IS NOT NULL))
);

COMMENT ON TABLE clinical.medications IS 'MedicationRequest projection. requester, performer, dispenseRequest, insurance, identifier, note are dropped. Labels from the RxNorm ingredient class list (antidepressants -> R+PSY, antiretrovirals -> V+HIV, OAT -> R+ETH, controlled -> R).';

CREATE INDEX medications_patient_authored_idx ON clinical.medications (patient_key, authored_at DESC);
CREATE INDEX medications_patient_code_idx     ON clinical.medications (patient_key, code);
CREATE INDEX medications_encounter_idx        ON clinical.medications (encounter_id);
CREATE INDEX medications_reason_idx           ON clinical.medications (reason_condition_id);
CREATE INDEX medications_sensitivity_idx      ON clinical.medications USING gin (sensitivity);

CREATE TRIGGER medications_touch_updated_at
    BEFORE UPDATE ON clinical.medications
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- AllergyIntolerance
--------------------------------------------------------------------------------

CREATE TABLE clinical.allergies (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id             text NOT NULL UNIQUE DEFAULT clinical.cite_id('alg'),
    source_id           text NOT NULL UNIQUE,
    patient_key         text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id        uuid,
    clinical_status     text CHECK (clinical_status = ANY (clinical.vs_allergy_clinical_status())),
    verification_status text CHECK (verification_status = ANY (clinical.vs_allergy_verification_status())),
    type                text CHECK (type = ANY (clinical.vs_allergy_type())),
    category            text[] NOT NULL DEFAULT '{}' CHECK (category <@ clinical.vs_allergy_category()),
    criticality         text CHECK (criticality = ANY (clinical.vs_allergy_criticality())),
    code                text,                                                              -- code.coding (SNOMED / RxNorm / UNII)
    code_system         text,
    display             text,
    reaction_code       text,                                                              -- reaction[0].manifestation[0].coding
    reaction_system     text,
    reaction_display    text,
    severity            text CHECK (severity = ANY (clinical.vs_reaction_severity())),      -- reaction[0].severity
    recorded_date       date,                                                              -- AllergyIntolerance.recordedDate
    onset_date          date,                                                              -- AllergyIntolerance.onsetDateTime
    confidentiality     text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity         text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource            jsonb NOT NULL DEFAULT '{}'
                        CHECK (jsonb_typeof(resource) = 'object'
                               AND (resource - ARRAY['resourceType', 'clinicalStatus', 'verificationStatus', 'type', 'category',
                                                     'criticality', 'code', 'reaction', 'recordedDate', 'onsetDateTime']::text[]) = '{}'::jsonb),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    CHECK ((code IS NULL) = (code_system IS NULL)),
    CHECK ((reaction_code IS NULL) = (reaction_system IS NULL))
);

COMMENT ON TABLE clinical.allergies IS 'AllergyIntolerance projection. recorder, asserter, note, identifier are dropped. dietary_staff sees category @> {food} rows only.';

CREATE INDEX allergies_patient_idx      ON clinical.allergies (patient_key);
CREATE INDEX allergies_encounter_idx    ON clinical.allergies (encounter_id);
CREATE INDEX allergies_category_idx     ON clinical.allergies USING gin (category);
CREATE INDEX allergies_sensitivity_idx  ON clinical.allergies USING gin (sensitivity);

CREATE TRIGGER allergies_touch_updated_at
    BEFORE UPDATE ON clinical.allergies
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- DocumentReference -> notes (metadata + pointer; text lives sanitized in MinIO,
-- chunks in Qdrant). Raw note text is never stored in Postgres.
--------------------------------------------------------------------------------

CREATE TABLE clinical.notes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id         text NOT NULL UNIQUE DEFAULT clinical.cite_id('note'),
    source_id       text NOT NULL UNIQUE,
    patient_key     text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id    uuid,
    status          text NOT NULL DEFAULT 'current' CHECK (status = ANY (clinical.vs_document_reference_status())),
    type_code       text,                                                                  -- DocumentReference.type.coding (LOINC, e.g. 34117-2)
    type_system     text,
    type_display    text,
    category        text,                                                                  -- category[0].coding.code (clinical-note)
    authored_at     timestamptz,                                                           -- DocumentReference.date / context.period.start
    sanitized_ref   text,                                                                  -- MinIO object key of the Presidio output
    internal        boolean NOT NULL DEFAULT false,                                        -- clinician-internal; omitted from the self view
    provenance      text NOT NULL DEFAULT 'clinical' CHECK (provenance = ANY (clinical.vs_note_provenance())),
    published       boolean NOT NULL DEFAULT false,                                        -- publication gate; tools read published rows only
    deid_version    text,                                                                  -- Presidio package + recogniser policy version
    chunk_count     integer CHECK (chunk_count IS NULL OR chunk_count >= 0),
    confidentiality text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity     text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource        jsonb NOT NULL DEFAULT '{}'
                    CHECK (jsonb_typeof(resource) = 'object'
                           AND (resource - ARRAY['resourceType', 'status', 'type', 'category', 'date']::text[]) = '{}'::jsonb),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    CHECK ((type_code IS NULL) = (type_system IS NULL)),
    -- A note cannot be published without sanitized text and a recorded de-identification policy.
    CHECK (NOT published OR (sanitized_ref IS NOT NULL AND deid_version IS NOT NULL))
);

COMMENT ON TABLE clinical.notes IS 'DocumentReference projection. content.attachment.data is decoded, de-identified, stored in MinIO (sanitized_ref) and chunked into Qdrant; author, custodian, authenticator, identifier are dropped. The DiagnosticReport duplicate (category 34117-2) is never ingested.';

CREATE INDEX notes_patient_published_idx ON clinical.notes (patient_key, published, internal);
CREATE INDEX notes_patient_authored_idx  ON clinical.notes (patient_key, authored_at DESC);
CREATE INDEX notes_encounter_idx         ON clinical.notes (encounter_id);
CREATE INDEX notes_sensitivity_idx       ON clinical.notes USING gin (sensitivity);

CREATE TRIGGER notes_touch_updated_at
    BEFORE UPDATE ON clinical.notes
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- DiagnosticReport (non-note): LAB rows group observations into panels,
-- imaging rows (clinical.vs_imaging_category()) are the report-text tier served
-- by /tools/imaging.
--------------------------------------------------------------------------------

CREATE TABLE clinical.diagnostic_reports (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id            text NOT NULL UNIQUE DEFAULT clinical.cite_id('rpt'),
    source_id          text NOT NULL UNIQUE,
    patient_key        text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id       uuid,
    status             text NOT NULL CHECK (status = ANY (clinical.vs_diagnostic_report_status())),
    category           text NOT NULL CHECK (category <> '34117-2'),                      -- category[0].coding.code: v2-0074 (LAB, RAD, ...) or DICOM (CT, MR, US)
    code               text NOT NULL,                                                      -- DiagnosticReport.code.coding (LOINC); 1..1
    code_system        text,
    display            text,
    effective_at       timestamptz,                                                        -- effectiveDateTime
    issued_at          timestamptz,                                                        -- issued
    conclusion_text    text,                                                               -- conclusion, after Presidio
    conclusion_code    text,                                                               -- conclusionCode[0].coding
    conclusion_system  text,
    conclusion_display text,
    study_id           uuid,                                                               -- imagingStudy[0]
    report_ref         text,                                                               -- MinIO reports/ object key of the sanitized presentedForm (imaging only)
    confidentiality    text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity        text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource           jsonb NOT NULL DEFAULT '{}'
                       CHECK (jsonb_typeof(resource) = 'object'
                              AND (resource - ARRAY['resourceType', 'status', 'category', 'code', 'effectiveDateTime', 'issued',
                                                    'conclusion', 'conclusionCode']::text[]) = '{}'::jsonb),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, patient_key),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    FOREIGN KEY (study_id, patient_key) REFERENCES clinical.studies (id, patient_key)
        ON DELETE SET NULL (study_id),
    CHECK ((code IS NULL) = (code_system IS NULL)),
    CHECK ((conclusion_code IS NULL) = (conclusion_system IS NULL)),
    -- presentedForm text is kept only for imaging reports.
    CHECK (report_ref IS NULL OR category = ANY (clinical.vs_imaging_category()))
);

COMMENT ON TABLE clinical.diagnostic_reports IS 'DiagnosticReport projection for LAB panels and imaging reports. performer, resultsInterpreter, identifier are dropped. Rows with category 34117-2 (note duplicates) are rejected by CHECK; report_ref is allowed only for imaging categories.';

CREATE INDEX diagnostic_reports_patient_effective_idx ON clinical.diagnostic_reports (patient_key, effective_at DESC);
CREATE INDEX diagnostic_reports_category_idx          ON clinical.diagnostic_reports (patient_key, category);
CREATE INDEX diagnostic_reports_study_idx             ON clinical.diagnostic_reports (study_id);
CREATE INDEX diagnostic_reports_encounter_idx         ON clinical.diagnostic_reports (encounter_id);
CREATE INDEX diagnostic_reports_sensitivity_idx       ON clinical.diagnostic_reports USING gin (sensitivity);

CREATE TRIGGER diagnostic_reports_touch_updated_at
    BEFORE UPDATE ON clinical.diagnostic_reports
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

-- DiagnosticReport.result[] -> Observation. patient_key on the link row lets both
-- foreign keys carry it, so a report can only group its own patient's observations.
CREATE TABLE clinical.diagnostic_report_results (
    report_id      uuid NOT NULL,
    observation_id uuid NOT NULL,
    patient_key    text NOT NULL,
    PRIMARY KEY (report_id, observation_id),
    FOREIGN KEY (report_id, patient_key)      REFERENCES clinical.diagnostic_reports (id, patient_key) ON DELETE CASCADE,
    FOREIGN KEY (observation_id, patient_key) REFERENCES clinical.observations (id, patient_key)      ON DELETE CASCADE
);

CREATE INDEX diagnostic_report_results_observation_idx ON clinical.diagnostic_report_results (observation_id);

-- The name the build plan and /tools/imaging use for the report-text tier.
CREATE VIEW clinical.imaging_reports AS
    SELECT *
    FROM clinical.diagnostic_reports
    WHERE category = ANY (clinical.vs_imaging_category());

COMMENT ON VIEW clinical.imaging_reports IS 'DiagnosticReport rows whose category is in clinical.vs_imaging_category() (v2-0074 imaging sections and DICOM modalities). Served as text by /tools/imaging; never pixels.';

--------------------------------------------------------------------------------
-- Optional resources (created empty now so Day-3 adoption needs no migration)
--------------------------------------------------------------------------------

-- Immunization
CREATE TABLE clinical.immunizations (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id         text NOT NULL UNIQUE DEFAULT clinical.cite_id('imm'),
    source_id       text NOT NULL UNIQUE,
    patient_key     text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id    uuid,
    status          text NOT NULL CHECK (status = ANY (clinical.vs_immunization_status())),
    code            text NOT NULL,                                                         -- vaccineCode.coding (CVX); 1..1
    code_system     text,
    display         text,
    occurred_at     timestamptz,                                                           -- occurrenceDateTime
    primary_source  boolean,                                                               -- primarySource
    confidentiality text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity     text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource        jsonb NOT NULL DEFAULT '{}'
                    CHECK (jsonb_typeof(resource) = 'object'
                           AND (resource - ARRAY['resourceType', 'status', 'vaccineCode', 'occurrenceDateTime', 'primarySource']::text[]) = '{}'::jsonb),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    CHECK ((code IS NULL) = (code_system IS NULL))
);

CREATE INDEX immunizations_patient_occurred_idx ON clinical.immunizations (patient_key, occurred_at DESC);
CREATE INDEX immunizations_encounter_idx        ON clinical.immunizations (encounter_id);
CREATE INDEX immunizations_sensitivity_idx      ON clinical.immunizations USING gin (sensitivity);

CREATE TRIGGER immunizations_touch_updated_at
    BEFORE UPDATE ON clinical.immunizations
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

-- Procedure
CREATE TABLE clinical.procedures (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id             text NOT NULL UNIQUE DEFAULT clinical.cite_id('proc'),
    source_id           text NOT NULL UNIQUE,
    patient_key         text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id        uuid,
    status              text NOT NULL CHECK (status = ANY (clinical.vs_event_status())),
    code                text,                                                              -- Procedure.code.coding (SNOMED); 0..1
    code_system         text,
    display             text,
    performed_start     timestamptz,                                                       -- performedPeriod.start / performedDateTime
    performed_end       timestamptz,                                                       -- performedPeriod.end
    reason_condition_id uuid,                                                              -- reasonReference[0] -> Condition
    confidentiality     text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity         text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource            jsonb NOT NULL DEFAULT '{}'
                        CHECK (jsonb_typeof(resource) = 'object'
                               AND (resource - ARRAY['resourceType', 'status', 'code', 'performedPeriod', 'performedDateTime',
                                                     'reasonReference']::text[]) = '{}'::jsonb),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id),
    FOREIGN KEY (reason_condition_id, patient_key) REFERENCES clinical.conditions (id, patient_key)
        ON DELETE SET NULL (reason_condition_id),
    CHECK ((code IS NULL) = (code_system IS NULL)),
    CHECK (performed_end IS NULL OR performed_start IS NULL OR performed_end >= performed_start)
);

CREATE INDEX procedures_patient_performed_idx ON clinical.procedures (patient_key, performed_start DESC);
CREATE INDEX procedures_patient_code_idx      ON clinical.procedures (patient_key, code);
CREATE INDEX procedures_encounter_idx         ON clinical.procedures (encounter_id);
CREATE INDEX procedures_sensitivity_idx       ON clinical.procedures USING gin (sensitivity);

CREATE TRIGGER procedures_touch_updated_at
    BEFORE UPDATE ON clinical.procedures
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

-- NutritionOrder (hand-seeded; Synthea does not emit it)
CREATE TABLE clinical.diet_orders (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id                 text NOT NULL UNIQUE DEFAULT clinical.cite_id('diet'),
    source_id               text NOT NULL UNIQUE,
    patient_key             text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    encounter_id            uuid,
    status                  text NOT NULL CHECK (status = ANY (clinical.vs_request_status())),
    intent                  text NOT NULL CHECK (intent = ANY (clinical.vs_request_intent())),
    ordered_at              timestamptz,                                                   -- NutritionOrder.dateTime
    diet_codes              text[] NOT NULL DEFAULT '{}',                                  -- oralDiet.type[].coding.code (SNOMED CT)
    texture                 text,                                                          -- oralDiet.texture[0].modifier.coding.code
    fluid_consistency       text,                                                          -- oralDiet.fluidConsistencyType[0].coding.code
    exclude_food_modifiers  text[] NOT NULL DEFAULT '{}',                                  -- neutral codes (no-pork, no-shellfish); never a religion label
    allergy_ids             uuid[] NOT NULL DEFAULT '{}',                                  -- allergyIntolerance[] -> clinical.allergies.id
    ward                    text,                                                          -- scope for dietary_staff
    confidentiality         text NOT NULL DEFAULT 'N' CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity             text[] NOT NULL DEFAULT '{}' CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource                jsonb NOT NULL DEFAULT '{}'
                            CHECK (jsonb_typeof(resource) = 'object'
                                   AND (resource - ARRAY['resourceType', 'status', 'intent', 'dateTime', 'oralDiet',
                                                         'excludeFoodModifier']::text[]) = '{}'::jsonb),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (encounter_id, patient_key) REFERENCES clinical.encounters (id, patient_key)
        ON DELETE SET NULL (encounter_id)
);

COMMENT ON TABLE clinical.diet_orders IS 'NutritionOrder projection for the dietary_staff persona. A renal diet implies kidney disease: an irreducible inference recorded on the threat-model page.';

CREATE INDEX diet_orders_patient_idx     ON clinical.diet_orders (patient_key);
CREATE INDEX diet_orders_ward_idx        ON clinical.diet_orders (ward);
CREATE INDEX diet_orders_sensitivity_idx ON clinical.diet_orders USING gin (sensitivity);

CREATE TRIGGER diet_orders_touch_updated_at
    BEFORE UPDATE ON clinical.diet_orders
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- Terminology: subsumption closure for label rules
--------------------------------------------------------------------------------

CREATE TABLE clinical.concept_closure (
    system     text NOT NULL,                                                              -- e.g. http://snomed.info/sct
    ancestor   text NOT NULL,
    descendant text NOT NULL,
    PRIMARY KEY (system, ancestor, descendant)
);

COMMENT ON TABLE clinical.concept_closure IS 'Transitive is-a closure loaded by the worker for the hierarchies label rules need (SNOMED 74732009 mental disorder, 86406008 HIV infection, ...). Include the reflexive row so a query on ancestor also matches the ancestor itself.';

CREATE INDEX concept_closure_descendant_idx ON clinical.concept_closure (system, descendant);

--------------------------------------------------------------------------------
-- Column policy: what the aggregate path and output rails must treat specially
--------------------------------------------------------------------------------

CREATE TABLE clinical.column_policy (
    table_name    text NOT NULL,
    column_name   text NOT NULL,
    class         text NOT NULL CHECK (class = ANY (clinical.vs_column_class())),
    aggregate_dim boolean NOT NULL DEFAULT false,
    PRIMARY KEY (table_name, column_name)
);

COMMENT ON TABLE clinical.column_policy IS 'Column classification. Every key, label, quasi_identifier and pointer column is listed; unlisted columns are class clinical and not an aggregate dimension. quasi_identifier columns are banded or date-shifted before any aggregate; pointer and key columns are never returned to the agent (cite_id is the citation handle, exposed separately).';

-- Explicit classifications: quasi-identifiers, pointers, note flags, and the
-- clinical columns the researcher path may group by.
INSERT INTO clinical.column_policy (table_name, column_name, class, aggregate_dim) VALUES
    -- patients
    ('patients', 'sex',               'quasi_identifier', true),
    ('patients', 'birth_year',        'quasi_identifier', true),
    ('patients', 'deceased',          'clinical',         true),
    ('patients', 'deceased_year',     'quasi_identifier', false),
    -- encounters
    ('encounters', 'status',          'clinical',         true),
    ('encounters', 'class',           'clinical',         true),
    ('encounters', 'type_code',       'clinical',         true),
    ('encounters', 'dept',            'clinical',         true),
    ('encounters', 'started_at',      'quasi_identifier', false),
    ('encounters', 'ended_at',        'quasi_identifier', false),
    -- conditions
    ('conditions', 'code',            'clinical',         true),
    ('conditions', 'clinical_status', 'clinical',         true),
    ('conditions', 'category',        'clinical',         true),
    ('conditions', 'onset_date',      'quasi_identifier', false),
    ('conditions', 'abatement_date',  'quasi_identifier', false),
    ('conditions', 'recorded_date',   'quasi_identifier', false),
    -- observations
    ('observations', 'code',           'clinical',         true),
    ('observations', 'category',       'clinical',         true),
    ('observations', 'interpretation', 'clinical',         true),
    ('observations', 'effective_at',   'quasi_identifier', false),
    ('observations', 'issued_at',      'quasi_identifier', false),
    -- medications
    ('medications', 'code',           'clinical',         true),
    ('medications', 'status',         'clinical',         true),
    ('medications', 'authored_at',    'quasi_identifier', false),
    -- allergies
    ('allergies', 'code',             'clinical',         true),
    ('allergies', 'category',         'clinical',         true),
    ('allergies', 'recorded_date',    'quasi_identifier', false),
    ('allergies', 'onset_date',       'quasi_identifier', false),
    -- notes
    ('notes', 'sanitized_ref',        'pointer',          false),
    ('notes', 'internal',             'label',            false),
    ('notes', 'published',            'label',            false),
    ('notes', 'provenance',           'label',            false),
    ('notes', 'authored_at',          'quasi_identifier', false),
    -- studies
    ('studies', 'modality',           'clinical',         true),
    ('studies', 'orthanc_id',         'pointer',          false),
    ('studies', 'study_at',           'quasi_identifier', false),
    -- diagnostic_reports
    ('diagnostic_reports', 'category',     'clinical',         true),
    ('diagnostic_reports', 'report_ref',   'pointer',          false),
    ('diagnostic_reports', 'effective_at', 'quasi_identifier', false),
    ('diagnostic_reports', 'issued_at',    'quasi_identifier', false),
    -- optional resources
    ('immunizations', 'code',         'clinical',         true),
    ('immunizations', 'occurred_at',  'quasi_identifier', false),
    ('procedures', 'code',            'clinical',         true),
    ('procedures', 'performed_start', 'quasi_identifier', false),
    ('procedures', 'performed_end',   'quasi_identifier', false),
    ('diet_orders', 'diet_codes',     'clinical',         true),
    ('diet_orders', 'ward',           'clinical',         true),
    ('diet_orders', 'ordered_at',     'quasi_identifier', false);

-- Generated classifications from the catalog, so every table gets them without
-- hand-listing. Explicit rows above win (ON CONFLICT DO NOTHING).
INSERT INTO clinical.column_policy (table_name, column_name, class, aggregate_dim)
SELECT c.table_name, c.column_name, 'key', false
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = 'clinical'
  AND c.column_name IN ('id', 'cite_id', 'source_id', 'patient_key', 'encounter_id', 'parent_id',
                        'reason_condition_id', 'study_id', 'report_id', 'observation_id', 'allergy_ids')
ON CONFLICT DO NOTHING;

INSERT INTO clinical.column_policy (table_name, column_name, class, aggregate_dim)
SELECT c.table_name, c.column_name, 'label', false
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = 'clinical'
  AND c.column_name IN ('confidentiality', 'sensitivity')
ON CONFLICT DO NOTHING;
