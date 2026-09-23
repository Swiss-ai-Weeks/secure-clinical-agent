# Patient360 backend (policy spine)

FastAPI service implementing Build Plan §4–5: sessions, PDP, run tokens, `/tools/query` (including aggregates), `/tools/notes`, `/tools/imaging`, `/chat` (in-proc), `/media/sign`, uploads, the four human writes, identity banner, and audit listing.

## Layout

```text
backend/app/
├── pyproject.toml, uv.lock, Dockerfile      # uv project, Python 3.12
├── patient360/
│   ├── main.py            # app factory: uvicorn --factory patient360.main:create_app
│   ├── config.py          # PATIENT360_* settings
│   ├── deps.py            # real stores (Postgres, OpenFGA, OpenBao) or fakes in tests
│   ├── db.py              # psycopg pool as p360_app (autocommit)
│   ├── errors.py          # byte-identical 404, 403 with reason code, 503 transient, 401
│   ├── audit.py           # one row per decision / tool call / login / write; reader queries; fails closed
│   ├── fga.py             # OpenFGA HTTP client: store by name, model pinned, current_time on every check, Write/Read
│   ├── vault.py           # OpenBao KV: resolve_self (login -> p_xxx), read_identity (p_xxx -> banner)
│   ├── humanwrites.py     # consent grant / revoke / list, break-glass: tuple + audit row ordering (§4.2)
│   ├── identity.py        # identity_banner: PDP-checked name/DOB/sex/MRN for the dashboard
│   ├── devlogin.py + devlogin.demo.json   # the only names in the backend (staff, for the switcher)
│   ├── auth/              # sessions.py, runtoken.py, subject.py (cookie or Bearer), router.py (/auth)
│   ├── pdp/               # models.py (§4.1 types), relations.py (§4.2 tables, §3 allowlists), rules.py
│   ├── tools/             # schemas.py, datasets.py (allowlisted columns), reader.py, query.py, router.py
│   └── routers/           # me.py, consents.py, break_glass.py, identity.py, audit.py, dev.py
└── tests/                 # offline: PDP matrices, uniform 404, run tokens, redaction, consents, break-glass, identity
    └── integration/       # live stores; skipped unless PATIENT360_DB_DSN is set
```

## Run

As a compose service (build context is `backend/`, so the image includes `guardrails/`; see [backend/deploy/patient360/compose.yaml](../deploy/patient360/compose.yaml)):

```bash
docker compose --env-file backend/deploy/patient360/.env -f backend/deploy/patient360/compose.yaml up -d --build openbao-init backend
curl -s http://127.0.0.1:8080/healthz      # {"status":"ok","policy_version":"fga:01K..."}
```

Startup refuses to proceed when the OpenFGA store `patient360-grants` is missing or ambiguous; the newest authorization model id is pinned and stamped on every audit row as `policy_version`. `openbao-init` must have completed: it writes the vault policies and the two fixed-id tokens (see "Vault tokens").

Locally, against stores published on loopback:

```bash
cd backend/app && uv sync
PATIENT360_DB_DSN=postgres://p360_app:$PATIENT360_APP_PASSWORD@127.0.0.1:5432/fhir \
PATIENT360_OPENFGA_URL=http://127.0.0.1:8091 PATIENT360_OPENFGA_KEY=$PATIENT360_OPENFGA_KEY \
PATIENT360_LINKAGE_URL=http://127.0.0.1:8200 PATIENT360_LINKAGE_TOKEN=$PATIENT360_LINKAGE_BACKEND_TOKEN \
PATIENT360_RUN_TOKEN_SECRET=$(openssl rand -hex 32) PATIENT360_DEV=true PATIENT360_COOKIE_SECURE=false \
uv run uvicorn --factory patient360.main:create_app --port 8080
```

Settings (all `PATIENT360_*`): `DB_DSN`, `OPENFGA_URL`, `OPENFGA_KEY`, `OPENFGA_STORE_NAME`, `LINKAGE_URL`, `LINKAGE_TOKEN` (the read-only backend token), `LINKAGE_MOUNT`, `RUN_TOKEN_SECRET`, `RUN_TOKEN_ISSUER`, `RUN_TOKEN_AUDIENCE`, `RUN_TOKEN_TTL_SECONDS` (600), `COOKIE_NAME`, `COOKIE_SECURE`, `SESSION_INACTIVITY_SECONDS` (3600), `SESSION_ABSOLUTE_SECONDS` (86400), `CONSENT_MAX_DAYS` (365), `BREAK_GLASS_MINUTES` (60), `BREAK_GLASS_PER_HOUR` (3), `ADOLESCENT_AGE` (14), `MAJORITY_AGE` (18), `K_MIN` (5), `K_MIN_CMS` (false → 11), `DEV`, `DEVLOGIN_PATH`.

## Vault tokens

OpenBao holds the only copies of `login -> p_xxx` (`linkage/self/{user_id}`) and `p_xxx -> identity` (`linkage/identity/{patient_key}`). `openbao-init` ([stores/init/openbao.sh](../deploy/patient360/stores/init/openbao.sh)) uses the root token once per `up` to write two policies and create two tokens with ids taken from the environment:

| Token | Policy | May | Used by |
|---|---|---|---|
| `PATIENT360_LINKAGE_BACKEND_TOKEN` | `p360-backend` | read `linkage/self/*`, `linkage/identity/*` | the `backend` service (`resolve_self`, `identity_banner`, `break_glass_identity`) |
| `PATIENT360_LINKAGE_WORKER_TOKEN` | `p360-worker` | create/update/read `linkage/*` | `seed_demo.py` (`register`), the ingestion worker |
| `PATIENT360_LINKAGE_TOKEN` | root | everything | `openbao` and `openbao-init` only |

The init script fails if the backend token can write. OpenBao runs in `-dev` mode (unsealed, in-memory): after a restart, `openbao-init` re-runs on `up` and `seed_demo.py` must be re-run to restore the identities. That is a lab limitation, recorded here and in `docs/threat-model.md`.

## Tests

```bash
cd backend/app
uv run pytest -q                 # offline, in-memory stores (fakes.py holds the demo permissions)
uv run ruff check . && uv run ruff format --check .
uv run pytest -m integration -q  # live stores; needs PATIENT360_DB_DSN etc., see tests/integration/
```

## Identity and channels

| Credential | Channel | Accepted by | How it is resolved |
|---|---|---|---|
| Session cookie `p360_session` | `dashboard` | every endpoint | sha256(cookie) looked up in `identity.sessions`; must be unrevoked and within both expiries; inactivity expiry slides |
| `Authorization: Bearer <at+JWT>` | `agent` | `/tools/*` only | signature, `typ`, `iss`, `aud`, `exp`, `act.sub`, `jti`, `sid`; the `sid` session must still be live, so logout revokes every token minted from it |

Identity never comes from a request body. `user_id`, `role`, and similar keys in tool arguments are ignored and recorded on the audit row as `detail.ignored_identity_args`.

## Endpoints

`POST /auth/dev-login` `{login, on_duty=true, auth_level=1}` → sets the cookie; returns `{user_id, display, role, department, self_patient_id, panels, session}`. `on_duty` and `auth_level` (1 or 2, the NIST AAL) are demo toggles for §9 steps 8 and step-up. Logins: `chen`, `rivera`, `okafor`, `nair`, `maria`, `diego`, `lindqvist`, `haller` (Nina Haller, legal guardian of `p_104`). Writes a `login` row and, for patient and caregiver roles, an `identity_resolve` row for the vault call.

`POST /auth/logout` → 204, revokes the session (and every run token bound to it). `GET /auth/dev-personas` (dev only) lists the switcher entries.

`GET /me` → `{user_id, display, role, department, credential_level, self_patient_id, datasets[], panels[], policy_version, session{expires_at, absolute_expires_at, auth_level, on_duty}}`. `datasets` is the per-patient allowlist for the role; `panels` is what the dashboard should render.

`POST /tools/query` `{patient_key, dataset, filters?, aggregate?}` with `dataset ∈ {labs, conditions, meds, encounters, allergies, diet}` and `filters ⊂ {since, until, code, category, active_only, limit ≤ 1000}`.

- 200 `{patient_key, dataset, rows[], row_count, redacted_count, suppressed_cells, obligations, decision{effect, reason_code, policy_id, policy_version, relation}, audit_id}`. Rows carry `cite_id` as the citation handle plus allowlisted clinical columns and the labels; surrogate ids, source ids, foreign keys and pointers are never selected. A redacted row is `{cite_id, confidentiality, redacted: true, redact_reason}`. Booked and pending appointments are merged into the `encounters` dataset.
- Aggregate: `{dataset, aggregate:{group_by, measure:count, project_id?}}`. Researcher needs `project_id` (`cohort_2026` in the demo); attending and dietary staff are scoped by `list_objects`. Cells are `{dims, count, suppressed}`; `k_min` is echoed on `obligations`. Complementary suppression blanks the last unsuppressed sibling. A same-dataset overlap (one filter equality different) is the uniform 404.
- 404 uniform `OperationOutcome` (`not-found`, "Resource not found"): unauthorized, nonexistent, dataset outside the role, researcher on the per-patient path, patient role on a foreign key. Byte-identical in every case.
- 403 `OperationOutcome` (`security`) with `details.coding[0].code` = reason (`off_duty_step_up_required`, `agent_write_forbidden`) and the audit id in `extension`.
- 503 `transient` when OpenFGA or the audit store is unavailable; nothing is read.

`POST /tools/availability` `{department?, practitioner_user_id?}` → `{slots[{practitioner_user_id, department, start, end}], count}`. Read-only; opaque practitioner ids, no names.

`POST /tools/notes` `{patient_key, question}` → PDP `can_read_notes`, then a server-built Qdrant filter (`patient_key`, `published=true`, allowed confidentiality, `internal=false` for self). Rivera does not receive V psych text. Diego's expired `caregiver_notes` is the uniform 404.

`POST /tools/imaging` `{patient_key}` → report text for attending/consultant, metadata for care_team/self. Never pixels.

`POST /chat` `{question, patient_key?}` (cookie only) → in-proc agent: mint run token, call query/notes, apply guardrails. Ask is live.

`POST /media/sign` + `GET /media/{token}/...` → dashboard-only pixels/documents.

`POST /uploads` multipart `{patient_key, file}` → quarantine, sanitize, patient-reported note.

`GET /audit` → newest rows for this user (auditor sees all). `GET /audit/{id}` → one row.

`GET /redteam` → YAML case catalog.

`POST /dev/run-token` `{agent_id="agent:dev"}` (dev only, cookie only) → `{access_token, expires_in, jti, sub, act, aud}`. Stands in for `/chat` minting a token into the OpenShell credential store.

### Human writes (cookie only; the run token's `aud` and the PDP's agent-channel rule are two independent walls)

`POST /consents` `{patient_key, grantee_user_id, relation, expiry?, start?, justification?}` → 201 `ConsentOut`. `relation ∈ {caregiver, caregiver_notes, blocked, care_team, consultant}`; every relation but `blocked` needs an `expiry` (≤ `CONSENT_MAX_DAYS` after `start`, default now). Writes the OpenFGA tuple, then the `consent_granted` audit row; if the row fails the tuple is deleted and the call is a 503. The row's id is the consent id. A live duplicate is 409 `consent_exists`; an expired or future duplicate is renewed by replacing its window. 422 `expiry_required` / `expiry_before_start` / `window_too_long`.

`POST /consents/{consent_id}/revoke` → 200 `{consent_id, patient_key, grantee_user_id, relation, revoked_at, tuple_removed, audit_id}`. Deletes the tuple, then writes `consent_revoked` (one retry; access is already gone). 409 `already_revoked`.

`GET /consents?patient=p_xxx` → `{patient_key, consents[], audit_id}`. Joins OpenFGA Read (what is enforced) with the `consent_granted` / `consent_revoked` rows (how it got that way). `status ∈ {active, pending, expired, revoked, removed, store_only}`; `store_only` is a tuple with no consent record (loaded by `openfga-init` or re-imported after a revoke), shown so enforcement is never hidden. `seeded` marks the demo grants `seed_demo.py` recorded.

Grant authority (Build Plan §4.2), checked by the PDP with the same uniform not-found for foreign patients:

| Subject | Basis | May grant | May revoke |
|---|---|---|---|
| `patient` on own record | self match (OpenFGA not consulted) | `caregiver`, `caregiver_notes`, `blocked` | the same, whoever granted |
| `caregiver` on own record (a parent who is also a patient) | self match | the same | the same |
| holder of `can_delegate` (attending, not blocked) | one OpenFGA check | `care_team`, `consultant` | only rows whose `granted_by` is themselves (`not_granted_by_subject` otherwise) |
| holder of `can_consent` (legal guardian of a minor, not blocked) | one OpenFGA check, `basis = guardian` | `caregiver`, `caregiver_notes`, `blocked` on the minor's record | the same, whoever granted |
| anyone else | | uniform 404 (`delegate_authority_missing`) | |

The grantee must be an active `identity.users` row whose role matches the relation (`grantee_role_mismatch`), and not the subject (`grantee_invalid`). Wrong relation for the authority is 403 `relation_not_grantable`. The `guardian` relation itself is not grantable through the API: it is a registration act the worker records (`tuples.demo.yaml` and `seed_demo.py` for the demo) with `expiry` set to the day of majority, so access lapses on that day without anyone acting.

### Minors

A guardian logs in with the `caregiver` role and reaches the child through the `guardian` tuple (clinical rows, notes, diet, scheduling, identity banner; no report text or pixels). Between `ADOLESCENT_AGE` (14) and `MAJORITY_AGE` (18), every `caregiver`-role reader of that patient, guardian or named caregiver alike, gets `R` and `V` rows redacted with reason `adolescent_confidential`: confidential adolescent care. The age comes from `clinical.patients.birth_year`, resolved before the decision and recorded on it as `detail.patient_age`; it only ever narrows a permit. Clinicians and the adolescent's own login (`patient` role, self match) are not affected. Capacity of judgement is a clinical determination the system records as a self login, not a birthday.

`POST /break-glass` `{patient_key, justification (20–1000 chars)}` → 201 `{patient_key, start, expiry, compliance_flag: true, audit_id, decision_audit_id, identity, identity_audit_id}`. Roles `attending`, `care_team`, `consultant`; on duty; AAL2 (`step_up_required` at AAL1). Writes an `emergency` tuple with `active_window = [now, now + BREAK_GLASS_MINUTES)`, then a `break_glass` row (`purpose_of_event = BTG`, `detail.justification`, `detail.compliance_flag`), then `break_glass_identity`: the vault banner, audited as `identity_resolve` with purpose `BTG`. `BREAK_GLASS_PER_HOUR` activations per user, then 429. `blocked` still wins inside OpenFGA: a blocked clinician's activation is recorded but grants nothing.

While an activation is live, every permitted `/tools/query` read by that user on that patient is labelled: the decision row gets `purpose_of_event = BTG`, `detail.break_glass_audit_id`, and the response carries `decision.compliance_flag = true`. The activation is looked up in the audit log, so the PDP keeps checking permissions and never the raw `emergency` relation.

`GET /patients/{patient_key}/identity` → `{patient_key, given_name, family_name, birth_date, sex, mrn, purpose_of_event, compliance_flag, audit_id, identity_audit_id}`. Self, or a live `can_read_clinical` for `attending`, `care_team`, `consultant`, `caregiver`. Researchers, dietary staff, the agent channel, and missing vault records all get the uniform 404 (the agent channel is a deny in the PDP, surfaced as 401 because the endpoint accepts cookies only). Address, phone, and national id stay in the vault; no endpoint returns them.

`POST /appointments` `{patient_key, practitioner_user_id, start, end?, dept?, service_type?}` → 201. Cookie only. Self match, or `can_schedule`. Practitioner must be an active attending / care_team / consultant. Writes `appointment_booked`.

`PATCH /appointments/{id}` `{status: "cancelled"}` → 200. Booker, practitioner, or self only; anyone else is the uniform 404. 409 `already_cancelled`.

## PDP (patient360/pdp)

`evaluate(subject, resource, context, check)` in §4.1 order:

1. Explicit deny: agent channel with a non-read action; care role (`attending`, `care_team`, `consultant`, `dietary_staff`) off duty → `off_duty_step_up_required`; `patient` role on any key other than the session's `self_patient_id` → reported as not-found (`self_mismatch`), OpenFGA not consulted; dataset outside the role allowlist (FHIR plan §3) → not-found (`aggregate_only` for researchers, else `dataset_not_allowed`).
2. Self match: `patient` on own key → permit with `exclude_internal`.
3. Relationship: one OpenFGA check with `context.current_time`. Relation from the §4.2 table: `can_read_diet` for `diet` and for a dietary worker's `allergies`, else `can_read_clinical`. `false` → not-found (`relationship_missing_or_expired`).
4. Obligations, applied row-wise after the read: `care_team` → `REDACT` on `R` and `V`; `caregiver` reading a patient aged `ADOLESCENT_AGE..MAJORITY_AGE-1` → `adolescent_confidential` on `R` and `V`; any non-self subject at AAL1 → `REDACT` on `V` with reason `step_up_required`; `dietary_staff` → `allergy_category = food`.

Every call writes a `decision` row (`policy_id`, `policy_version`, `reason_code`, `entity_query` = base64 of the parameters, `session_id`, `jti`, `detail.obligations`); a permitted read adds a `tool_call` row with the row and redaction counts.

Writes take the same entry point with `Context.action ∈ {consent_grant, consent_revoke, break_glass}` and a `WriteTarget` (relation, grantee, grantee role from `identity.users`, `granted_by` from the consent row). The agent channel is denied before anything else (`agent_write_forbidden`). Reads of `identity` and `consents` resources follow the tables above. `can_delegate` (`attending but not blocked`) and `can_consent` (`guardian but not blocked`) are the two OpenFGA permissions that gate writes, chosen by role (`AUTHORITY_BY_ROLE`), so the PDP still never checks a raw grant relation.

## Demo walkthrough (Build Plan §9, curl)

Prerequisites: stores and `backend` up, `openfga-init` done, and the seed loaded:

```bash
cd backend/app && uv run python ../ingestion/seed_demo.py      # reads backend/deploy/patient360/.env
```

```bash
B=http://127.0.0.1:8080; J='content-type: application/json'
q() { curl -s -b "$1" -X POST $B/tools/query -H "$J" -d "{\"patient_key\":\"$2\",\"dataset\":\"$3\"}"; }

# 1. Dr. Chen, attending, on duty, AAL2: full answer with citations
curl -s -c /tmp/chen -X POST $B/auth/dev-login -H "$J" -d '{"login":"chen","auth_level":2}' | jq -c '{role,panels}'
curl -s -b /tmp/chen $B/me | jq -c '{role,datasets,policy_version}'
q /tmp/chen p_101 labs | jq -c '{row_count,redacted_count,audit_id,first:.rows[0]|{cite_id,display,value_num,unit}}'
q /tmp/chen p_101 meds | jq -c '[.rows[]|{cite_id,display,status,confidentiality}]'
curl -s -b /tmp/chen -X POST $B/tools/notes -H "$J" -d '{"patient_key":"p_101","question":"medication"}' | jq -c '{chunk_count,notes:[.notes[]|.type_display]}'
curl -s -b /tmp/chen -X POST $B/chat -H "$J" -d '{"question":"What changed?","patient_key":"p_101"}' | jq -c '{refused,answer}'

# 2. Nurse Rivera, care team: the psych rows are redacted, and it shows
curl -s -c /tmp/rivera -X POST $B/auth/dev-login -H "$J" -d '{"login":"rivera","auth_level":2}' >/dev/null
q /tmp/rivera p_101 conditions | jq -c '{redacted_count,obligations,redacted:[.rows[]|select(.redacted)]}'

# 3. Dr. Okafor, consultant: p_101 in window, p_102 expired in August
curl -s -c /tmp/okafor -X POST $B/auth/dev-login -H "$J" -d '{"login":"okafor","auth_level":2}' >/dev/null
q /tmp/okafor p_101 meds | jq -c '{row_count,decision}';  q /tmp/okafor p_102 meds

# 4. Priya Nair, researcher: uniform 404 on any patient; aggregates only, with k-min
#    Seed-only (5 patients) almost all suppress at k=5 — that is the correct demo.
#    Unsuppressed cells need the Synthea 100-patient load; the project grant is still
#    cohort_2026 (a capability, not a membership list).
curl -s -c /tmp/nair -X POST $B/auth/dev-login -H "$J" -d '{"login":"nair"}' >/dev/null
q /tmp/nair p_101 labs
curl -s -b /tmp/nair -X POST $B/tools/query -H "$J" \
  -d '{"dataset":"conditions","aggregate":{"group_by":["code"],"project_id":"cohort_2026"}}' \
  | jq -c '{row_count,suppressed_cells,k_min:.obligations.k_min,cells:[.rows[]|{dims,count,suppressed}]}'
# a second query that only adds filters.code is overlap_blocked (same 404 body)
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/nair -X POST $B/tools/query -H "$J" \
  -d '{"dataset":"conditions","filters":{"code":"44054006"},"aggregate":{"group_by":["code"],"project_id":"cohort_2026"}}'

# 5. Maria Santos, patient: not_found on p_101, own record p_103 without OpenFGA
curl -s -c /tmp/maria -X POST $B/auth/dev-login -H "$J" -d '{"login":"maria"}' | jq -c '{role,self_patient_id}'
q /tmp/maria p_101 labs;  q /tmp/maria p_103 encounters | jq -c '{row_count,decision}'

# 6. Diego Santos, caregiver: meds for p_103; any other patient is not found.
#    Booked appointments (Maria's cardiology slot, or a new book) show on encounters.
curl -s -c /tmp/diego -X POST $B/auth/dev-login -H "$J" -d '{"login":"diego"}' >/dev/null
q /tmp/diego p_103 meds | jq -c '{row_count}';  q /tmp/diego p_101 meds
q /tmp/diego p_103 encounters | jq -c '{rows:[.rows[]|{cite_id,status,dept,started_at}]}'
curl -s -b /tmp/diego -X POST $B/tools/availability -H "$J" -d '{"department":"cardiology"}' | jq -c '{count,first:.slots[0]}'
SLOT=$(curl -s -b /tmp/diego -X POST $B/tools/availability -H "$J" -d '{"practitioner_user_id":"u_okafor"}' | jq -r '.slots[0]')
curl -s -b /tmp/diego -X POST $B/appointments -H "$J" -d "{\"patient_key\":\"p_103\",\"practitioner_user_id\":\"u_okafor\",\"start\":$(echo "$SLOT" | jq .start),\"end\":$(echo "$SLOT" | jq .end),\"dept\":\"cardiology\"}" | jq -c '{id,status,created_by}'

# 7. Unauthenticated: 401 before the PDP (no audit row)
curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/tools/query -H "$J" -d '{"patient_key":"p_101","dataset":"labs"}'

# 8. Dr. Chen off duty: 403 with the reason and the audit id
curl -s -c /tmp/chen_off -X POST $B/auth/dev-login -H "$J" -d '{"login":"chen","on_duty":false}' >/dev/null
q /tmp/chen_off p_101 labs | jq -c '{code:.issue[0].details.coding[0].code, audit:.extension[0].valueString}'

# 9. Dr. Chen on p_205 (unassigned) vs p_999 (nonexistent): byte-identical
q /tmp/chen p_205 labs > /tmp/a; q /tmp/chen p_999 labs > /tmp/b; cmp /tmp/a /tmp/b && echo identical

# 12. Tomas Lindqvist, dietary staff on shift: diet and food allergies for p_101 only
curl -s -c /tmp/chef -X POST $B/auth/dev-login -H "$J" -d '{"login":"lindqvist"}' >/dev/null
q /tmp/chef p_101 allergies | jq -c '{rows:[.rows[].display],obligations,relation:.decision.relation}'
q /tmp/chef p_101 diet | jq -c '{rows:[.rows[]|{cite_id,diet_codes,ward}]}';  q /tmp/chef p_101 labs

# Agent channel: a run token reads through /tools/*, is refused on /me, dies with the session
T=$(curl -s -b /tmp/chen -X POST $B/dev/run-token -H "$J" -d '{"agent_id":"agent:sbx_01"}' | jq -r .access_token)
curl -s -X POST $B/tools/query -H "$J" -H "Authorization: Bearer $T" -d '{"patient_key":"p_101","dataset":"labs"}' | jq -c '{row_count,decision}'
curl -s -o /dev/null -w '%{http_code}\n' $B/me -H "Authorization: Bearer $T"                       # 401
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/chen -X POST $B/auth/logout                          # 204
curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/tools/query -H "$J" -H "Authorization: Bearer $T" -d '{"patient_key":"p_101","dataset":"labs"}'  # 401

# Identity banner: a name only for self or a live relationship, never through the agent
curl -s -b /tmp/chen $B/patients/p_101/identity | jq -c .          # Elisabeth Keller, DOB, sex, MRN; no address/phone/national id
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/nair $B/patients/p_101/identity      # 404
curl -s -o /dev/null -w '%{http_code}\n' $B/patients/p_101/identity -H "Authorization: Bearer $T"   # 401

# 10. Dr. Chen break-glass on p_205: typed justification, one-hour emergency tuple, BTG rows, compliance flag
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/chen $B/patients/p_205/identity     # 404 before
BG=$(curl -s -b /tmp/chen -X POST $B/break-glass -H "$J" \
  -d '{"patient_key":"p_205","justification":"Unresponsive patient in ED, prior records needed for anticoagulation decision"}')
echo "$BG" | jq -c '{expiry,compliance_flag,identity,audit_id}'
q /tmp/chen p_205 labs | jq -c '{row_count,purpose:.decision.purpose_of_event,compliance_flag:.decision.compliance_flag}'   # BTG, true
curl -s -b /tmp/chen $B/audit/$(echo "$BG" | jq -r .audit_id) | jq -c '{event_type,purpose_of_event,detail:{justification:.detail.justification,expiry:.detail.expiry}}'
curl -s -c /tmp/chen1 -X POST $B/auth/dev-login -H "$J" -d '{"login":"chen","auth_level":1}' >/dev/null
curl -s -b /tmp/chen1 -X POST $B/break-glass -H "$J" -d '{"patient_key":"p_205","justification":"AAL1 attempt, must be refused with step_up_required"}' | jq -c '.issue[0].details.coding[0].code'

# 11. Maria revokes Diego's consent live: his next call is not found, the portal shows the revoked entry
curl -s -b /tmp/maria $B/consents?patient=p_103 | jq -c '.consents[]|{grantee_user_id,relation,status,seeded,consent_id}'
CID=$(curl -s -b /tmp/maria $B/consents?patient=p_103 | jq -r '.consents[]|select(.grantee_user_id=="u_diego" and .relation=="caregiver")|.consent_id')
q /tmp/diego p_103 meds | jq -c '{row_count}'                                          # 200 before
curl -s -b /tmp/maria -X POST $B/consents/$CID/revoke | jq -c '{revoked_at,tuple_removed,audit_id}'
q /tmp/diego p_103 meds                                                                # uniform 404
curl -s -b /tmp/maria $B/consents?patient=p_103 | jq -c '.consents[]|select(.grantee_user_id=="u_diego")|{relation,status,revoked_by}'
# and back: Maria grants again with a window and a justification
curl -s -b /tmp/maria -X POST $B/consents -H "$J" -d "{\"patient_key\":\"p_103\",\"grantee_user_id\":\"u_diego\",\"relation\":\"caregiver\",\"expiry\":\"$(date -u -v+30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)\",\"justification\":\"my son helps with my medication\"}" | jq -c '{status,consent_id}'
# Chen (attending) may delegate care_team / consultant, never caregiver or blocked, and only on own patients
curl -s -b /tmp/chen -X POST $B/consents -H "$J" -d '{"patient_key":"p_101","grantee_user_id":"u_diego","relation":"caregiver","expiry":"2027-01-01T00:00:00Z"}' | jq -c '.issue[0].details.coding[0].code'   # relation_not_grantable
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/rivera -X POST $B/consents -H "$J" -d '{"patient_key":"p_101","grantee_user_id":"u_okafor","relation":"consultant","expiry":"2027-01-01T00:00:00Z"}'   # 404

# 13. Nina Haller, legal guardian of Lea (p_104, 14): reads her labs, the adolescent-clinic rows are
#     redacted, she names and removes a caregiver on Lea's behalf, and sees nothing of anyone else.
#     Her guardian tuple expires on Lea's 18th birthday (2030-05-03) with no further action.
curl -s -c /tmp/haller -X POST $B/auth/dev-login -H "$J" -d '{"login":"haller","auth_level":2}' | jq -c '{role,self_patient_id}'
q /tmp/haller p_104 labs | jq -c '{row_count,redacted_count,relation:.decision.relation}'
q /tmp/haller p_104 conditions | jq -c '{redacted_count,obligations,redacted:[.rows[]|select(.redacted)]}'      # adolescent_confidential
q /tmp/haller p_104 encounters | jq -c '[.rows[]|{cite_id,dept,redacted}]'                                       # adolescent-medicine visit redacted
curl -s -b /tmp/haller $B/patients/p_104/identity | jq -c '{given_name,family_name,birth_date}'
curl -s -b /tmp/haller $B/consents?patient=p_104 | jq -c '.consents[]|{grantee_user_id,relation,status,expiry,seeded}'
GC=$(curl -s -b /tmp/haller -X POST $B/consents -H "$J" -d "{\"patient_key\":\"p_104\",\"grantee_user_id\":\"u_diego\",\"relation\":\"caregiver\",\"expiry\":\"$(date -u -v+30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)\",\"justification\":\"uncle drives her to appointments\"}" | jq -r .consent_id)
q /tmp/diego p_104 conditions | jq -c '{row_count,redacted_count}'                                               # the uncle gets the same age rule
curl -s -b /tmp/haller -X POST $B/consents/$GC/revoke | jq -c '{revoked_at,tuple_removed}';  q /tmp/diego p_104 labs   # 404
q /tmp/haller p_103 labs;  curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/haller $B/patients/p_101/identity        # 404, 404
curl -s -b /tmp/haller -X POST $B/consents -H "$J" -d '{"patient_key":"p_104","grantee_user_id":"u_rivera","relation":"care_team","expiry":"2027-01-01T00:00:00Z"}' | jq -c '.issue[0].details.coding[0].code'   # relation_not_grantable

# Audit: read a decision row, then verify the chain as the auditor role
curl -s -b /tmp/rivera $B/audit/$(q /tmp/rivera p_101 labs | jq -r .audit_id) | jq -c '{event_type,reason_code,policy_version,row_hash}'
docker exec -e PGPASSWORD="$PATIENT360_AUDITOR_PASSWORD" patient360-postgres \
  psql -U p360_auditor -d fhir -Atc 'SELECT audit.verify_chain() IS NULL AS chain_ok, count(*) FROM audit.audit_events'
docker exec -e PGPASSWORD="$PATIENT360_AUDITOR_PASSWORD" patient360-postgres \
  psql -U p360_auditor -d fhir -Atc "SELECT purpose_of_event, count(*) FROM audit.audit_events GROUP BY 1 ORDER BY 1"
```

A revoked demo tuple comes back on the next `compose up` because `openfga-init` re-imports `tuples.demo.yaml`; the listing then shows the revoked record next to a `store_only` entry for the re-imported tuple. `backend/ingestion/seed_grants.py` rewrites demo-relative windows and records `consent_granted` rows with `detail.seeded=true`. It does not grant care relations on the leftover Synthea ~97.

The same sequence, including steps 10, 11, and 13, runs offline against the real schema and the real Postgres code paths (sessions, audit chain and reader queries, dataset SQL, role privileges) on an embedded PostgreSQL 16 with `pgcrypto` shimmed; the offline unit suite covers the PDP matrices (reads, consent authority incl. guardianship, break-glass, identity, adolescent rule), byte-identical 404s, run-token rejections, redaction, column allowlists, the §4.2 write ordering, and the OpenFGA client request shapes.
