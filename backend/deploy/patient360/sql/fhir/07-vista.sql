-- VISTA-3D overlay persist. Idempotent on volumes that already ran 00–06.

CREATE OR REPLACE FUNCTION audit.vs_event_type() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT ARRAY['decision', 'tool_call', 'consent_granted', 'consent_revoked', 'break_glass',
                   'login', 'logout', 'step_up', 'media_sign', 'media_fetch', 'ingest', 'upload',
                   'identity_resolve', 'appointment_booked', 'appointment_cancelled',
                   'vista_reprocess']::text[] $$;
COMMENT ON FUNCTION audit.vs_event_type() IS
    'Patient360 audit event types; exported as AuditEvent.type + subtype.';

GRANT INSERT, UPDATE ON clinical.diagnostic_reports TO p360_app;
