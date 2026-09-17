-- Patient360 `fhir` database: audit schema.
--
-- One append-only, hash-chained log. Rows are shaped so GET /audit/{id}?format=fhir
-- maps 1:1 onto FHIR R4 AuditEvent (docs/Patient360-FHIR-Resource-Plan.md §4.1):
--   event_type        -> type + subtype
--   recorded_at       -> recorded
--   agent_user        -> agent[0].who (opaque u_xxx), requestor = true
--   agent_software    -> agent[1].who (Device), type 110150 Application
--   purpose_of_event  -> purposeOfEvent / agent[0].purposeOfUse (v3-ActReason PurposeOfUse)
--   entity_patient    -> entity[0].what (Patient/p_xxx), role 1 Patient
--   entity_resource   -> entity[1].what
--   entity_query      -> entity[1].query (base64 of the tool parameters)
--   outcome           -> outcome (0 success, 4 minor, 8 serious, 12 major failure)
--   reason_code, policy_id, policy_version -> outcomeDesc + entity.detail[]
--   prev_hash, row_hash -> extension patient360-audit-chain
--
-- Consent has no table of its own: consent_granted / consent_revoked / break_glass
-- rows here, written in the same handler as the OpenFGA tuple, are the record.
--
-- Enforcement: no role other than the superuser owner holds UPDATE/DELETE/TRUNCATE,
-- and triggers raise on each of them even for the owner. Superusers can still
-- disable triggers, which is why no service connects as the superuser.
--
-- Ordering: chain_hash() takes an advisory lock, then assigns seq from
-- audit_events_seq, then reads the previous row_hash. Doing all three under the
-- lock makes lock order, seq order and chain order the same thing; an identity
-- column would be assigned before the trigger runs and could interleave.
-- Assumes READ COMMITTED (the default).
--
-- Writers: the lock is held until the writing transaction commits, so every
-- other audit insert waits behind it. Insert audit rows in their own short
-- transaction (autocommit); never inside a long request transaction.

--------------------------------------------------------------------------------
-- audit_events
--------------------------------------------------------------------------------

CREATE SEQUENCE audit.audit_events_seq AS bigint;

CREATE TABLE audit.audit_events (
    seq              bigint NOT NULL UNIQUE,                                               -- set by chain_hash() under the lock; caller-supplied values are overwritten
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    event_type       text NOT NULL CHECK (event_type = ANY (audit.vs_event_type())),
    agent_user       text,                                                                 -- u_xxx acting on behalf of; NULL for system events
    agent_software   text,                                                                 -- backend, agent:sbx_xx, ingest-worker, media-proxy
    purpose_of_event text CHECK (purpose_of_event = ANY (audit.vs_purpose_of_use())),      -- v3-PurposeOfUse
    entity_patient   text,                                                                 -- p_xxx; may reference a nonexistent patient (uniform 404), so no FK
    entity_resource  text,                                                                 -- dataset, note cite_id, study cite_id, tuple, ...
    entity_query     text,                                                                 -- base64 tool parameters
    outcome          text NOT NULL CHECK (outcome = ANY (audit.vs_outcome())),              -- AuditEvent.outcome
    outcome_desc     text,
    policy_id        text,
    policy_version   text,
    reason_code      text,                                                                 -- grant_expired, off_duty_step_up_required, aggregate_only, ...
    session_id       text,                                                                 -- hex of identity.sessions.session_hash; no FK: sessions are deleted, audit rows are not
    jti              text,
    detail           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(detail) = 'object'),  -- obligations, justification; for `ingest`: Synthea version, seeds, reference date, per-type counts, adversarial cite_ids; never names
    prev_hash        bytea,
    row_hash         bytea NOT NULL                                                        -- set by trigger; NOT NULL is checked after BEFORE triggers
);

ALTER SEQUENCE audit.audit_events_seq OWNED BY audit.audit_events.seq;

COMMENT ON TABLE audit.audit_events IS 'Append-only, SHA-256 hash-chained event log. One row per PDP decision, tool call, human action, login, and ingest run. Exported as FHIR AuditEvent.';
COMMENT ON COLUMN audit.audit_events.entity_query IS 'Base64 of the tool parameters as received; identity fields present in tool arguments are logged here and ignored by the PDP.';

CREATE INDEX audit_events_patient_idx  ON audit.audit_events (entity_patient, recorded_at DESC);
CREATE INDEX audit_events_agent_idx    ON audit.audit_events (agent_user, recorded_at DESC);
CREATE INDEX audit_events_session_idx  ON audit.audit_events (session_id);
CREATE INDEX audit_events_type_idx     ON audit.audit_events (event_type, recorded_at DESC);

--------------------------------------------------------------------------------
-- Hash chain
--------------------------------------------------------------------------------

-- Deterministic byte serialisation of the business columns. jsonb normalises key
-- order, and the timestamp is rendered in UTC so verification does not depend on
-- the session TimeZone. seq, prev_hash and row_hash are excluded by construction.
CREATE FUNCTION audit.canonical_payload(r audit.audit_events) RETURNS bytea
LANGUAGE sql STABLE
AS $$
    SELECT convert_to(
        jsonb_build_object(
            'id',               r.id::text,
            'recorded_at',      to_char(r.recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
            'event_type',       r.event_type,
            'agent_user',       r.agent_user,
            'agent_software',   r.agent_software,
            'purpose_of_event', r.purpose_of_event,
            'entity_patient',   r.entity_patient,
            'entity_resource',  r.entity_resource,
            'entity_query',     r.entity_query,
            'outcome',          r.outcome,
            'outcome_desc',     r.outcome_desc,
            'policy_id',        r.policy_id,
            'policy_version',   r.policy_version,
            'reason_code',      r.reason_code,
            'session_id',       r.session_id,
            'jti',              r.jti,
            'detail',           r.detail
        )::text,
        'UTF8')
$$;

-- SECURITY DEFINER: insert-only writers (p360_worker) hold no SELECT on the table
-- or USAGE on the sequence, yet the chain must read the previous row_hash and
-- draw the next seq. The function runs as its owner (the superuser that ran
-- initdb) with a pinned search_path.
CREATE FUNCTION audit.chain_hash() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_prev bytea;
BEGIN
    -- Serialise concurrent inserts; the lock is released at commit or rollback.
    PERFORM pg_advisory_xact_lock(hashtext('audit.audit_events'));
    -- seq is drawn under the lock so it increases in chain order.
    NEW.seq := nextval('audit.audit_events_seq');
    SELECT row_hash INTO v_prev FROM audit.audit_events ORDER BY seq DESC LIMIT 1;
    NEW.prev_hash := v_prev;
    NEW.row_hash  := public.digest(coalesce(v_prev, ''::bytea) || audit.canonical_payload(NEW), 'sha256');
    RETURN NEW;
END
$$;

-- Walks the chain in seq order. Returns the first seq whose prev_hash or
-- row_hash does not verify, or NULL when the whole chain is intact.
CREATE FUNCTION audit.verify_chain() RETURNS bigint
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    r      audit.audit_events%ROWTYPE;
    v_prev bytea := NULL;
BEGIN
    FOR r IN SELECT * FROM audit.audit_events ORDER BY seq LOOP
        IF r.prev_hash IS DISTINCT FROM v_prev
           OR r.row_hash <> public.digest(coalesce(v_prev, ''::bytea) || audit.canonical_payload(r), 'sha256') THEN
            RETURN r.seq;
        END IF;
        v_prev := r.row_hash;
    END LOOP;
    RETURN NULL;
END
$$;

--------------------------------------------------------------------------------
-- Immutability
--------------------------------------------------------------------------------

CREATE FUNCTION audit.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit.% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$;

CREATE TRIGGER audit_events_chain_hash
    BEFORE INSERT ON audit.audit_events
    FOR EACH ROW EXECUTE FUNCTION audit.chain_hash();

CREATE TRIGGER audit_events_forbid_update_delete
    BEFORE UPDATE OR DELETE ON audit.audit_events
    FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();

CREATE TRIGGER audit_events_forbid_truncate
    BEFORE TRUNCATE ON audit.audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation();

-- Fire regardless of session_replication_role.
ALTER TABLE audit.audit_events
    ENABLE ALWAYS TRIGGER audit_events_chain_hash,
    ENABLE ALWAYS TRIGGER audit_events_forbid_update_delete,
    ENABLE ALWAYS TRIGGER audit_events_forbid_truncate;

--------------------------------------------------------------------------------
-- Aggregate query log (overlap detection, per-session k-anonymity decay)
--------------------------------------------------------------------------------

CREATE TABLE audit.aggregate_query_log (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    session_id       text,
    user_id          text,
    dataset          text NOT NULL,
    group_by         text[] NOT NULL DEFAULT '{}',
    filters          jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(filters) = 'object'),
    cells            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(cells) = 'array'),   -- [{dims, count}] after suppression
    suppressed_cells integer NOT NULL DEFAULT 0 CHECK (suppressed_cells >= 0),
    k_min            integer CHECK (k_min IS NULL OR k_min >= 2),
    audit_id         uuid                                                                  -- audit_events.id of the decision; no FK
);

COMMENT ON TABLE audit.aggregate_query_log IS 'Every aggregate query the researcher path answered. The PDP reads a session''s prior rows to block differencing and complement attacks; the threat model records the residual multi-turn decay.';

CREATE INDEX aggregate_query_log_session_idx ON audit.aggregate_query_log (session_id, recorded_at DESC);
CREATE INDEX aggregate_query_log_user_idx    ON audit.aggregate_query_log (user_id, recorded_at DESC);

CREATE TRIGGER aggregate_query_log_forbid_update_delete
    BEFORE UPDATE OR DELETE ON audit.aggregate_query_log
    FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();

CREATE TRIGGER aggregate_query_log_forbid_truncate
    BEFORE TRUNCATE ON audit.aggregate_query_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation();

ALTER TABLE audit.aggregate_query_log
    ENABLE ALWAYS TRIGGER aggregate_query_log_forbid_update_delete,
    ENABLE ALWAYS TRIGGER aggregate_query_log_forbid_truncate;
