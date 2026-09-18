-- Appointments: the fourth human write (Build Plan §5.2).
-- Idempotent so seed_demo.py can apply it on volumes that already ran 00–05.

CREATE OR REPLACE FUNCTION clinical.vs_appointment_status() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['proposed', 'pending', 'booked', 'arrived', 'fulfilled', 'cancelled',
                   'noshow', 'entered-in-error', 'checked-in', 'waitlist']::text[] $$;
COMMENT ON FUNCTION clinical.vs_appointment_status() IS
    'http://hl7.org/fhir/ValueSet/appointmentstatus|4.0.1 (required) -> Appointment.status';

CREATE OR REPLACE FUNCTION audit.vs_event_type() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['decision', 'tool_call', 'consent_granted', 'consent_revoked', 'break_glass',
                   'login', 'logout', 'step_up', 'media_sign', 'media_fetch', 'ingest', 'upload',
                   'identity_resolve', 'appointment_booked', 'appointment_cancelled']::text[] $$;
COMMENT ON FUNCTION audit.vs_event_type() IS
    'Patient360 audit event types; exported as AuditEvent.type + subtype.';

CREATE TABLE IF NOT EXISTS clinical.appointments (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cite_id              text NOT NULL UNIQUE DEFAULT clinical.cite_id('apt'),
    source_id            text NOT NULL UNIQUE,
    patient_key          text NOT NULL REFERENCES clinical.patients (patient_key) ON DELETE CASCADE,
    practitioner_user_id text NOT NULL REFERENCES identity.users (user_id),
    status               text NOT NULL CHECK (status = ANY (clinical.vs_appointment_status())),
    start_at             timestamptz NOT NULL,
    end_at               timestamptz,
    dept                 text,
    service_type         text,
    service_type_system  text,
    service_type_display text,
    created_by           text NOT NULL REFERENCES identity.users (user_id),
    confidentiality      text NOT NULL DEFAULT 'N'
                         CHECK (confidentiality = ANY (clinical.vs_confidentiality())),
    sensitivity          text[] NOT NULL DEFAULT '{}'
                         CHECK (sensitivity <@ clinical.vs_sensitivity()),
    resource             jsonb NOT NULL DEFAULT '{}'
                         CHECK (jsonb_typeof(resource) = 'object'),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, patient_key),
    CHECK ((service_type IS NULL) = (service_type_system IS NULL)),
    CHECK (end_at IS NULL OR end_at > start_at)
);

COMMENT ON TABLE clinical.appointments IS
    'FHIR Appointment projection. First clinical table p360_app may INSERT/UPDATE.';

CREATE INDEX IF NOT EXISTS appointments_patient_start_idx
    ON clinical.appointments (patient_key, start_at);
CREATE INDEX IF NOT EXISTS appointments_practitioner_idx
    ON clinical.appointments (practitioner_user_id, start_at);

DROP TRIGGER IF EXISTS appointments_touch_updated_at ON clinical.appointments;
CREATE TRIGGER appointments_touch_updated_at
    BEFORE UPDATE ON clinical.appointments
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

INSERT INTO clinical.column_policy (table_name, column_name, class, aggregate_dim) VALUES
    ('appointments', 'status',     'clinical',         true),
    ('appointments', 'dept',       'clinical',         true),
    ('appointments', 'start_at',   'quasi_identifier', false),
    ('appointments', 'end_at',     'quasi_identifier', false)
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, UPDATE ON clinical.appointments TO p360_app;
GRANT SELECT, INSERT, UPDATE ON clinical.appointments TO p360_worker;
