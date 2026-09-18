-- Patient360 `fhir` database: privileges. Runs after every object exists.
--
--                 clinical                 identity                     audit
--   p360_app      SELECT                   SELECT INSERT UPDATE DELETE  SELECT INSERT
--   p360_worker   SELECT INSERT UPDATE     users: SELECT INSERT UPDATE  INSERT
--   p360_auditor  -                        -                            SELECT
--
-- Nobody but the superuser owner can ALTER, DROP, DELETE from clinical, or
-- UPDATE/DELETE/TRUNCATE audit. The worker has no DELETE: reprocessing uses
-- stable upserts. Source removals require an explicit future policy; retries
-- must never reset the database volume.

-- Deny-by-default on schemas.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA clinical FROM PUBLIC;
REVOKE ALL ON SCHEMA identity FROM PUBLIC;
REVOKE ALL ON SCHEMA audit FROM PUBLIC;

GRANT USAGE ON SCHEMA clinical TO p360_app, p360_worker;
GRANT USAGE ON SCHEMA identity TO p360_app, p360_worker;
GRANT USAGE ON SCHEMA audit    TO p360_app, p360_worker, p360_auditor;

-- clinical: tools read, worker upserts.
GRANT SELECT                 ON ALL TABLES IN SCHEMA clinical TO p360_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA clinical TO p360_worker;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA clinical TO p360_app, p360_worker;

-- identity: backend owns sessions and tokens; worker seeds personas only.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity TO p360_app;
GRANT SELECT, INSERT, UPDATE ON identity.users TO p360_worker;

-- audit: insert-only for writers, read for the backend's audit view and the auditor.
GRANT SELECT, INSERT ON audit.audit_events        TO p360_app;
GRANT INSERT         ON audit.audit_events        TO p360_worker;
GRANT SELECT         ON audit.audit_events        TO p360_auditor;
GRANT SELECT, INSERT ON audit.aggregate_query_log TO p360_app;
GRANT SELECT         ON audit.aggregate_query_log TO p360_auditor;
GRANT EXECUTE ON FUNCTION audit.verify_chain() TO p360_app, p360_auditor;
-- audit_events_seq needs no grant: chain_hash() draws it as SECURITY DEFINER.
-- Trigger functions cannot be invoked directly, but keep the definer function private anyway.
REVOKE EXECUTE ON FUNCTION audit.chain_hash() FROM PUBLIC;

-- Belt and braces: never granted, revoked anyway.
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM PUBLIC, p360_app, p360_worker, p360_auditor;
REVOKE DELETE, TRUNCATE ON ALL TABLES IN SCHEMA clinical FROM PUBLIC, p360_app, p360_worker;
