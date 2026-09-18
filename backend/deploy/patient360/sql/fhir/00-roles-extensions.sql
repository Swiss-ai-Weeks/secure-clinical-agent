-- Patient360 `fhir` database: extensions, schemas, roles, shared helpers, value sets.
--
-- Files in this directory run once, in name order, against an empty Postgres
-- volume (docker-entrypoint-initdb.d). Schema changes require dropping the
-- `postgres-fhir-data` volume; there is no in-place migration path here.
--
-- Layout
--   clinical  FHIR R4 projections (allowlisted elements, HL7 HCS labels)
--   identity  users, sessions (opaque ids only, no names)
--   audit     append-only, hash-chained events shaped like FHIR AuditEvent
--
-- Roles (passwords are set by 99-role-passwords.sh from the environment)
--   p360_app      FastAPI backend: reads clinical, owns sessions, writes audit
--   p360_worker   ingestion worker: upserts clinical, seeds users, writes audit
--   p360_auditor  read-only on audit
--   openfga       OpenFGA datastore role; owns the separate `openfga` database
--                 (98-openfga-datastore.sh) and cannot connect to `fhir`
-- The compose POSTGRES_USER (fhir_app) is a superuser and bypasses every
-- REVOKE below. It is for initdb and operators only; no service connects as it.
--
-- Value sets are `vs_*()` functions returning text[], one per FHIR value set
-- (or Patient360 code list), defined once here and referenced by CHECKs as
-- `col = ANY (schema.vs_x())` or `col <@ schema.vs_x()`. Each carries its FHIR
-- canonical URL and binding strength in its COMMENT. The worker reads the same
-- lists with e.g. `SELECT clinical.vs_observation_status()`.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA clinical;
CREATE SCHEMA identity;
CREATE SCHEMA audit;

COMMENT ON SCHEMA clinical IS 'FHIR R4 element projections keyed by opaque patient_key. Every row carries an HL7 HCS label.';
COMMENT ON SCHEMA identity IS 'Opaque user ids, roles, server-side sessions (hashed). Never names, logins, or persisted patient links. Run tokens are stateless JWTs bound to a session by sid.';
COMMENT ON SCHEMA audit    IS 'Append-only, hash-chained event log exportable as FHIR AuditEvent.';

-- Unqualified table names in application SQL resolve to the clinical schema.
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET search_path = clinical, public', current_database());
END
$$;

-- Roles are cluster-wide; guard against re-runs on a shared cluster.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'p360_app') THEN
        CREATE ROLE p360_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'p360_worker') THEN
        CREATE ROLE p360_worker NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'p360_auditor') THEN
        CREATE ROLE p360_auditor NOLOGIN;
    END IF;
END
$$;

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

-- Short random citation id shown to the agent (e.g. obs_7f3a9c21d0e4). Twelve
-- hex characters = 48 bits. 32 bits reaches a 50% chance of a collision at
-- ~65k rows, which a single observations table exceeds for 100 Synthea
-- patients; at 48 bits the expected number of collisions in 100k rows is ~2e-5.
-- Never derived from source ids and never sequential.
CREATE FUNCTION clinical.cite_id(prefix text) RETURNS text
LANGUAGE sql VOLATILE
AS $$
    SELECT prefix || '_' || encode(gen_random_bytes(6), 'hex')
$$;

-- The single place the "ages >= 90 are reported as 90+" rule lives.
-- Age is computed from birth year only, so it is approximate by design.
CREATE FUNCTION clinical.age_display(birth_year integer, at_date date DEFAULT current_date) RETURNS text
LANGUAGE sql STABLE
AS $$
    SELECT CASE
        WHEN birth_year IS NULL THEN NULL
        WHEN extract(year FROM at_date)::integer - birth_year >= 90 THEN '90+'
        ELSE (extract(year FROM at_date)::integer - birth_year)::text
    END
$$;

CREATE FUNCTION clinical.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

--------------------------------------------------------------------------------
-- Value sets: HL7 security labels
--------------------------------------------------------------------------------

CREATE FUNCTION clinical.vs_confidentiality() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['N', 'R', 'V']::text[] $$;
COMMENT ON FUNCTION clinical.vs_confidentiality() IS 'http://terminology.hl7.org/ValueSet/v3-Confidentiality (subset: N normal, R restricted, V very restricted)';

CREATE FUNCTION clinical.vs_sensitivity() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['PSY', 'ETH', 'HIV', 'STD', 'SEX', 'GDIS', 'SDV']::text[] $$;
COMMENT ON FUNCTION clinical.vs_sensitivity() IS 'http://terminology.hl7.org/ValueSet/v3-InformationSensitivityPolicy (subset). ETH is substance abuse; there is no SUD code.';

--------------------------------------------------------------------------------
-- Value sets: FHIR R4 (4.0.1) element bindings used by clinical tables
--------------------------------------------------------------------------------

CREATE FUNCTION clinical.vs_administrative_gender() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['male', 'female', 'other', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_administrative_gender() IS 'http://hl7.org/fhir/ValueSet/administrative-gender|4.0.1 (required) -> Patient.gender';

CREATE FUNCTION clinical.vs_encounter_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['planned', 'arrived', 'triaged', 'in-progress', 'onleave', 'finished', 'cancelled', 'entered-in-error', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_encounter_status() IS 'http://hl7.org/fhir/ValueSet/encounter-status|4.0.1 (required)';

CREATE FUNCTION clinical.vs_encounter_class() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['AMB', 'EMER', 'FLD', 'HH', 'IMP', 'ACUTE', 'NONAC', 'OBSENC', 'PRENC', 'SS', 'VR']::text[] $$;
COMMENT ON FUNCTION clinical.vs_encounter_class() IS 'http://terminology.hl7.org/ValueSet/v3-ActEncounterCode (extensible) -> Encounter.class';

CREATE FUNCTION clinical.vs_condition_clinical_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['active', 'recurrence', 'relapse', 'inactive', 'remission', 'resolved']::text[] $$;
COMMENT ON FUNCTION clinical.vs_condition_clinical_status() IS 'http://hl7.org/fhir/ValueSet/condition-clinical|4.0.1 (required)';

CREATE FUNCTION clinical.vs_condition_verification_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['unconfirmed', 'provisional', 'differential', 'confirmed', 'refuted', 'entered-in-error']::text[] $$;
COMMENT ON FUNCTION clinical.vs_condition_verification_status() IS 'http://hl7.org/fhir/ValueSet/condition-ver-status|4.0.1 (required)';

CREATE FUNCTION clinical.vs_condition_category() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['problem-list-item', 'encounter-diagnosis', 'health-concern']::text[] $$;
COMMENT ON FUNCTION clinical.vs_condition_category() IS 'http://hl7.org/fhir/ValueSet/condition-category|4.0.1 (extensible) plus US Core health-concern';

CREATE FUNCTION clinical.vs_observation_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['registered', 'preliminary', 'final', 'amended', 'corrected', 'cancelled', 'entered-in-error', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_observation_status() IS 'http://hl7.org/fhir/ValueSet/observation-status|4.0.1 (required)';

CREATE FUNCTION clinical.vs_observation_category() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['social-history', 'vital-signs', 'imaging', 'laboratory', 'procedure', 'survey', 'exam', 'therapy', 'activity',
                   'sdoh', 'functional-status', 'disability-status', 'cognitive-status',
                   'care-experience-preference', 'treatment-intervention-preference', 'clinical-test']::text[] $$;
COMMENT ON FUNCTION clinical.vs_observation_category() IS 'http://hl7.org/fhir/ValueSet/observation-category|4.0.1 (preferred) plus US Core 6.1 us-core-category codes';

CREATE FUNCTION clinical.vs_imaging_study_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['registered', 'available', 'cancelled', 'entered-in-error', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_imaging_study_status() IS 'http://hl7.org/fhir/ValueSet/imagingstudy-status|4.0.1 (required)';

CREATE FUNCTION clinical.vs_medication_request_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['active', 'on-hold', 'cancelled', 'completed', 'entered-in-error', 'stopped', 'draft', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_medication_request_status() IS 'http://hl7.org/fhir/ValueSet/medicationrequest-status|4.0.1 (required)';

-- Distinct from vs_request_intent(): MedicationRequest.intent has no `directive`.
CREATE FUNCTION clinical.vs_medication_request_intent() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['proposal', 'plan', 'order', 'original-order', 'reflex-order', 'filler-order', 'instance-order', 'option']::text[] $$;
COMMENT ON FUNCTION clinical.vs_medication_request_intent() IS 'http://hl7.org/fhir/ValueSet/medicationrequest-intent|4.0.1 (required)';

CREATE FUNCTION clinical.vs_units_of_time() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['s', 'min', 'h', 'd', 'wk', 'mo', 'a']::text[] $$;
COMMENT ON FUNCTION clinical.vs_units_of_time() IS 'http://hl7.org/fhir/ValueSet/units-of-time|4.0.1 (required) -> Timing.repeat.periodUnit';

CREATE FUNCTION clinical.vs_allergy_clinical_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['active', 'inactive', 'resolved']::text[] $$;
COMMENT ON FUNCTION clinical.vs_allergy_clinical_status() IS 'http://hl7.org/fhir/ValueSet/allergyintolerance-clinical|4.0.1 (required)';

CREATE FUNCTION clinical.vs_allergy_verification_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['unconfirmed', 'confirmed', 'refuted', 'entered-in-error']::text[] $$;
COMMENT ON FUNCTION clinical.vs_allergy_verification_status() IS 'http://hl7.org/fhir/ValueSet/allergyintolerance-verification|4.0.1 (required)';

CREATE FUNCTION clinical.vs_allergy_type() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['allergy', 'intolerance']::text[] $$;
COMMENT ON FUNCTION clinical.vs_allergy_type() IS 'http://hl7.org/fhir/ValueSet/allergy-intolerance-type|4.0.1 (required)';

CREATE FUNCTION clinical.vs_allergy_category() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['food', 'medication', 'environment', 'biologic']::text[] $$;
COMMENT ON FUNCTION clinical.vs_allergy_category() IS 'http://hl7.org/fhir/ValueSet/allergy-intolerance-category|4.0.1 (required)';

CREATE FUNCTION clinical.vs_allergy_criticality() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['low', 'high', 'unable-to-assess']::text[] $$;
COMMENT ON FUNCTION clinical.vs_allergy_criticality() IS 'http://hl7.org/fhir/ValueSet/allergy-intolerance-criticality|4.0.1 (required)';

CREATE FUNCTION clinical.vs_reaction_severity() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['mild', 'moderate', 'severe']::text[] $$;
COMMENT ON FUNCTION clinical.vs_reaction_severity() IS 'http://hl7.org/fhir/ValueSet/reaction-event-severity|4.0.1 (required)';

CREATE FUNCTION clinical.vs_document_reference_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['current', 'superseded', 'entered-in-error']::text[] $$;
COMMENT ON FUNCTION clinical.vs_document_reference_status() IS 'http://hl7.org/fhir/ValueSet/document-reference-status|4.0.1 (required)';

CREATE FUNCTION clinical.vs_diagnostic_report_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['registered', 'partial', 'preliminary', 'final', 'amended', 'corrected', 'appended', 'cancelled', 'entered-in-error', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_diagnostic_report_status() IS 'http://hl7.org/fhir/ValueSet/diagnostic-report-status|4.0.1 (required)';

-- DiagnosticReport categories that make a report part of the imaging tier.
CREATE FUNCTION clinical.vs_imaging_category() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['RAD', 'RUS', 'RX', 'NMR', 'NMS', 'CUS', 'VUS', 'OUS',
                   'CT', 'MR', 'US', 'CR', 'DX', 'NM', 'PT', 'MG', 'XA', 'RF']::text[] $$;
COMMENT ON FUNCTION clinical.vs_imaging_category() IS 'Patient360 subset of http://terminology.hl7.org/CodeSystem/v2-0074 (imaging service sections) plus DICOM acquisition modalities (CID 29). Drives the imaging_reports view and the report_ref CHECK.';

CREATE FUNCTION clinical.vs_immunization_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['completed', 'entered-in-error', 'not-done']::text[] $$;
COMMENT ON FUNCTION clinical.vs_immunization_status() IS 'http://hl7.org/fhir/ValueSet/immunization-status|4.0.1 (required)';

CREATE FUNCTION clinical.vs_event_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['preparation', 'in-progress', 'not-done', 'on-hold', 'stopped', 'completed', 'entered-in-error', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_event_status() IS 'http://hl7.org/fhir/ValueSet/event-status|4.0.1 (required) -> Procedure.status';

CREATE FUNCTION clinical.vs_request_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['draft', 'active', 'on-hold', 'revoked', 'completed', 'entered-in-error', 'unknown']::text[] $$;
COMMENT ON FUNCTION clinical.vs_request_status() IS 'http://hl7.org/fhir/ValueSet/request-status|4.0.1 (required) -> NutritionOrder.status';

-- Distinct from vs_medication_request_intent(): RequestIntent includes `directive`.
CREATE FUNCTION clinical.vs_request_intent() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['proposal', 'plan', 'directive', 'order', 'original-order', 'reflex-order', 'filler-order', 'instance-order', 'option']::text[] $$;
COMMENT ON FUNCTION clinical.vs_request_intent() IS 'http://hl7.org/fhir/ValueSet/request-intent|4.0.1 (required) -> NutritionOrder.intent';

--------------------------------------------------------------------------------
-- Value sets: Patient360 code lists (not FHIR)
--------------------------------------------------------------------------------

CREATE FUNCTION clinical.vs_note_provenance() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['clinical', 'generated', 'adversarial', 'patient-reported']::text[] $$;
COMMENT ON FUNCTION clinical.vs_note_provenance() IS 'Patient360: origin of a note. generated = LLM from history; adversarial = planted injection note; patient-reported = upload.';

CREATE FUNCTION clinical.vs_column_class() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['key', 'label', 'clinical', 'quasi_identifier', 'pointer']::text[] $$;
COMMENT ON FUNCTION clinical.vs_column_class() IS 'Patient360: classes in clinical.column_policy.';

CREATE FUNCTION identity.vs_user_role() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['attending', 'care_team', 'consultant', 'caregiver', 'patient', 'researcher', 'dietary_staff', 'auditor']::text[] $$;
COMMENT ON FUNCTION identity.vs_user_role() IS 'Patient360 personas. Relationships to patients are OpenFGA tuples, not roles.';

CREATE FUNCTION audit.vs_event_type() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['decision', 'tool_call', 'consent_granted', 'consent_revoked', 'break_glass', 'login', 'logout', 'step_up',
                   'media_sign', 'media_fetch', 'ingest', 'upload', 'identity_resolve']::text[] $$;
COMMENT ON FUNCTION audit.vs_event_type() IS 'Patient360 audit event types; exported as AuditEvent.type + subtype.';

CREATE FUNCTION audit.vs_purpose_of_use() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['TREAT', 'HRESCH', 'BTG', 'PATRQT', 'HOPERAT']::text[] $$;
COMMENT ON FUNCTION audit.vs_purpose_of_use() IS 'http://terminology.hl7.org/ValueSet/v3-PurposeOfUse (subset) -> AuditEvent.purposeOfEvent';

CREATE FUNCTION audit.vs_outcome() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['0', '4', '8', '12']::text[] $$;
COMMENT ON FUNCTION audit.vs_outcome() IS 'http://hl7.org/fhir/ValueSet/audit-event-outcome|4.0.1 (required): 0 success, 4 minor, 8 serious, 12 major failure';
