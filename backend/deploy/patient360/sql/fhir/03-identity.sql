-- Patient360 `fhir` database: identity schema.
--
-- What this schema answers: what role does u_xxx have; is u_xxx logged in, on
-- duty, stepped up; which run tokens are live. What it never contains: names,
-- logins, credentials, consents, or a persisted user -> patient link. The
-- login -> pseudonym mapping lives only in the vault; resolve_self copies it
-- into the session row for the session lifetime and nowhere else.
--
-- Session tokens are stored hashed. The cookie carries a CSPRNG 128-bit token;
-- the backend stores and looks up sha256(token) (session_hash), so a read of
-- this table yields no usable cookies. Audit rows reference a session by the
-- hex of session_hash.
--
-- Standards: NIST SP 800-63-4 (auth_level = AAL), OWASP ASVS 5.0 V7,
-- RFC 9068 / RFC 8693 (run tokens with act claim).

--------------------------------------------------------------------------------
-- Users
--------------------------------------------------------------------------------

CREATE TABLE identity.users (
    user_id          text PRIMARY KEY CHECK (user_id ~ '^u_[0-9a-z]+$'),
    role             text NOT NULL CHECK (role = ANY (identity.vs_user_role())),
    department       text,
    credential_level integer NOT NULL DEFAULT 1 CHECK (credential_level BETWEEN 0 AND 5),
    active           boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE identity.users IS 'Opaque user ids and roles. Names exist only in the dev-login map and the vault. Relationships to patients live in OpenFGA, never here.';

CREATE INDEX users_role_idx ON identity.users (role) WHERE active;

CREATE TRIGGER users_touch_updated_at
    BEFORE UPDATE ON identity.users
    FOR EACH ROW EXECUTE FUNCTION clinical.touch_updated_at();

--------------------------------------------------------------------------------
-- Sessions (server-side reference tokens)
--------------------------------------------------------------------------------

CREATE TABLE identity.sessions (
    session_hash        bytea PRIMARY KEY CHECK (octet_length(session_hash) = 32),        -- sha256 of the cookie token; the token itself is never stored
    user_id             text NOT NULL REFERENCES identity.users (user_id) ON DELETE CASCADE,
    created_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,                                              -- inactivity expiry (1 h for care roles)
    absolute_expires_at timestamptz NOT NULL,                                              -- absolute lifetime (24 h)
    auth_level          integer NOT NULL DEFAULT 1 CHECK (auth_level IN (1, 2)),           -- NIST AAL of the login event
    on_duty             boolean NOT NULL DEFAULT true,
    self_patient_id     text CHECK (self_patient_id IS NULL OR self_patient_id ~ '^p_[0-9a-z]+$'),
                                                                                           -- transient copy from vault.resolve_self; NO foreign key on purpose
    sandbox_id          text,                                                              -- OpenShell sandbox bound to this session
    revoked_at          timestamptz,
    CHECK (expires_at <= absolute_expires_at),
    CHECK (absolute_expires_at > created_at)
);

COMMENT ON TABLE identity.sessions IS 'One row per live session, keyed by sha256(cookie token). Rotate the token (new row) on login and step-up. self_patient_id is filled by one vault call at login and disappears with the row; it must never gain a foreign key or be copied elsewhere.';
COMMENT ON COLUMN identity.sessions.self_patient_id IS 'Transient. Patient and caregiver roles only. The PDP compares it in memory; OpenFGA is not consulted for self access.';

CREATE INDEX sessions_user_idx    ON identity.sessions (user_id);
CREATE INDEX sessions_expires_idx ON identity.sessions (expires_at) WHERE revoked_at IS NULL;

--------------------------------------------------------------------------------
-- Run tokens (RFC 9068 at+JWT with RFC 8693 act claim), one row per jti
--------------------------------------------------------------------------------

CREATE TABLE identity.run_tokens (
    jti          text PRIMARY KEY,                                                         -- not secret: the JWT is signed
    session_hash bytea NOT NULL REFERENCES identity.sessions (session_hash) ON DELETE CASCADE,
    subject    text NOT NULL CHECK (subject ~ '^user:u_[0-9a-z]+$'),                      -- sub
    actor      text CHECK (actor IS NULL OR actor ~ '^agent:'),                            -- act.sub
    audience   text NOT NULL DEFAULT 'patient360-tools',                                   -- aud
    issued_at  timestamptz NOT NULL DEFAULT now(),                                         -- iat
    expires_at timestamptz NOT NULL,                                                       -- exp (10 min)
    revoked_at timestamptz,
    CHECK (expires_at > issued_at)
);

COMMENT ON TABLE identity.run_tokens IS 'Registry of minted run tokens. Tool endpoints require the jti to exist, be unexpired, unrevoked, and belong to a live session. Ending a session cascades here, revoking every token minted from it.';

CREATE INDEX run_tokens_session_idx ON identity.run_tokens (session_hash);
CREATE INDEX run_tokens_expires_idx ON identity.run_tokens (expires_at) WHERE revoked_at IS NULL;
