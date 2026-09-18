# Patient360 backend

Backend source and deployment configuration live here, alongside the top-level `frontend/`. Run the commands below from the **repository root**.

```text
backend/
├── app/                 # FastAPI policy spine: sessions, PDP, run tokens, /tools/*, audit (uv project)
├── deploy/
│   ├── patient360/       # Compose, SQL, store initialization, environment template
│   ├── compose.hybrid.yaml
│   ├── hybrid.env       # Non-secret shell configuration for the legacy RAG overlay
│   └── blueprint.ref    # Pinned upstream NVIDIA RAG revision
├── ingestion/           # Synthea source worker, seed_demo.py, tests, research, remaining pipeline plan
├── docs/                # Backend architecture, runbooks, and historical verification
└── examples/            # Synthetic backend demo fixtures
```

Shared clinical/product documentation remains in [../docs/](../docs/). The repository's local Markdown tracker remains under [../.scratch/](../.scratch/).

## Patient360 configuration

```bash
cp backend/deploy/patient360/.env.example backend/deploy/patient360/.env
# Edit .env locally. Set passwords and the NVIDIA registry credential.
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml config --quiet
```

The local `.env` file is ignored by Git. `config --quiet` validates without printing rendered credentials. Compose resolves the SQL and initialization-script bind mounts relative to the relocated Compose file; keep those files together.

To start the configured stores:

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml up -d --build \
  postgres openfga-migrate openfga openfga-init qdrant qdrant-init openbao minio minio-init orthanc
```

`--build` is needed once for `openfga-init`, which is built from `stores/init/openfga-cli.Dockerfile` (the `fga` binary copied out of the distroless `openfga/cli` image into Alpine).

### Postgres `fhir` database

`backend/deploy/patient360/sql/fhir/` is the schema. The files run once, in name order, when the `postgres-fhir-data` volume is empty; Postgres never re-runs them. For an explicitly approved disposable demo reset, back up the database and recreate the volume with the commands below. Normal worker retries must not run this reset. The [2026-09-17 replacement evidence](ingestion/schema-integration.md) records the current server's verified bootstrap and backup.

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml rm -sf postgres
docker volume rm patient360_postgres-fhir-data
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml up -d postgres
```

Three schemas: `clinical` (FHIR R4 projections with HL7 HCS labels), `identity` (opaque users, hashed sessions), `audit` (append-only, hash-chained `audit_events`; immudb is retired behind `--profile legacy`). Each process connects as its own role, never as the superuser `fhir_app`:

| Process | Role | Privileges |
|---|---|---|
| FastAPI backend | `p360_app` | read `clinical`; read/write `identity`; insert and read `audit` |
| Ingestion worker | `p360_worker` | insert/update `clinical`; insert/update `identity.users`; insert `audit` |
| Auditor tooling | `p360_auditor` | read `audit` |
| OpenFGA | `openfga` | owns the separate database `openfga` (its datastore); cannot connect to `fhir` |
| initdb, operators | `fhir_app` | superuser; bypasses every `REVOKE`, so no service uses it |

`CONNECT` on `fhir` is granted only to the three `p360_*` roles, and `CONNECT` on `openfga` only to `openfga`, so grants cannot be read or edited behind the OpenFGA API and the grant store cannot see clinical data.

### OpenFGA grant store

`backend/deploy/patient360/stores/openfga/` holds the authorization model (`model.fga`), the demo grants (`tuples.demo.yaml`, Build Plan §9), and the store file (`store.fga.yaml`) that binds both together with the persona test matrix. Three object types: `patient` carries every per-patient permission, `project` the research cohorts, and `ward` the placement chain (`staff from admitted_to`) that gives dietary staff `can_read_diet` on the patients of their ward for the length of a shift. `openfga-init` imports the store file into the store named `patient360-grants` on every `up`; it reuses the existing store, ignores tuples already present, and writes one new immutable model version per run. The backend pins the newest model id at startup and records it on audit rows as `policy_version`.

Test the model offline, with no server and no Docker:

```bash
brew install openfga/tap/fga            # or a release binary from github.com/openfga/cli
fga model validate --file backend/deploy/patient360/stores/openfga/model.fga
fga model test --tests backend/deploy/patient360/stores/openfga/store.fga.yaml
```

Against the running instance (published on `127.0.0.1:8091`):

```bash
export FGA_API_URL=http://127.0.0.1:8091 FGA_API_TOKEN="$PATIENT360_OPENFGA_KEY"
fga store list
fga query check user:u_chen can_read_notes patient:p_101 \
  --store-id "$STORE_ID" --context '{"current_time":"2026-09-18T12:00:00Z"}'
```

Every grant is conditioned on `active_window`, so `--context` with `current_time` is required on every check. Tuples change only through the OpenFGA API: the backend's consent, break-glass, and booking endpoints, and the ingestion worker's `seed_grants.py`. A manual `fga tuple write` bypasses the audit trail and is an operator break-glass, not a workflow. The schema change in `98-openfga-datastore.sh` applies only on an empty volume (see the reset commands above).

### Backend service (policy spine)

`backend/app/` is the FastAPI service the Build Plan calls Track A: dev-login and hashed sessions, the PDP over OpenFGA, RFC 9068 run tokens, the fail-closed audit writer, `GET /me`, `POST /tools/query` with the uniform not-found and `REDACT` obligations, and the human writes: `POST /consents`, `POST /consents/{id}/revoke`, `GET /consents`, `POST /break-glass`, and `GET /patients/{key}/identity`. It is the `backend` compose service (`127.0.0.1:8080`), connects to Postgres as `p360_app`, resolves the OpenFGA store by name at startup, and reaches the linkage vault over the `patient360-linkage` network with a read-only token.

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml up -d --build openbao-init backend
cd backend/app && uv run python ../ingestion/seed_demo.py     # personas, p_101/p_102/p_103/p_205, consent rows, vault
curl -s http://127.0.0.1:8080/healthz
```

`seed_demo.py` connects as `p360_worker`, is idempotent (upserts on `patient_key` / `source_id`; consent rows by deterministic id), writes one `consent_granted` row per demo grant so the portal can list and revoke them, writes the `u_maria -> p_103` link and the four synthetic identity records into OpenBao with the worker token, and records one `ingest` audit row. Grants come from `openfga-init`, not from the seed.

### Linkage vault tokens

`openbao-init` runs on every `up` with the root token (`PATIENT360_LINKAGE_TOKEN`) and leaves two least-privilege tokens with fixed ids from `.env`: `PATIENT360_LINKAGE_BACKEND_TOKEN` (policy `p360-backend`: read `linkage/self/*` and `linkage/identity/*`) for the backend, and `PATIENT360_LINKAGE_WORKER_TOKEN` (policy `p360-worker`: create/update `linkage/*`) for `seed_demo.py` and the worker. The script fails if the backend token can write. OpenBao is in dev mode (in-memory): after a restart, `up` re-creates the tokens and `seed_demo.py` restores the identities. Endpoint contracts, the grant authority table, the PDP order, the offline test suite, and the §9 curl walkthrough (steps 1–12 minus the notes and imaging tools) are in [app/README.md](app/README.md).

To start all default services, including the local Nano, safety, and embedding models:

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml up -d
```

To inspect the current services:

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml ps
```

The optional `--profile ingest` enables VISTA-3D and MedGemma imaging services. It does not run the planned Synthea/Presidio pipeline. The configuration retains the existing project name, container names, networks, volumes, GPU assignments, and loopback ports; the folder move does not start, recreate, or migrate running containers.

## Ingestion

Start with [ingestion/README.md](ingestion/README.md) and [the proposed pipeline sequence](ingestion/plan.md). Future generation, FHIR projection, note processing, embedding, ACL metadata, worker code, and ingestion tests belong in `backend/ingestion/`. Deployment definitions remain in `backend/deploy/`.

The first source stage is implemented: `python3 backend/ingestion/worker.py run --profile smoke` generates or verifies/reuses a pinned 10-patient raw batch; `--profile seed` selects 100 patients. See [the worker runbook](ingestion/RUNBOOK.md) for artifact verification and remaining stages. This command does not populate the existing stores.

## NVIDIA RAG overlay

[deploy/compose.hybrid.yaml](deploy/compose.hybrid.yaml), [deploy/hybrid.env](deploy/hybrid.env), and [deploy/blueprint.ref](deploy/blueprint.ref) preserve the existing overlay. It depends on pinned upstream NVIDIA Compose files and is not a standalone Compose application. `hybrid.env` is shell configuration, not a Docker dotenv file.

The earlier `scripts/rag` and `scripts/patient360/run` launchers are absent from this checkout. Runbooks under [docs/](docs/) preserve historical commands and findings; they are not evidence that those tools or services currently work. Restore or implement backend launcher code under `backend/` when that work is undertaken.

Existing local runtime directories `.vendor/`, `.secrets/`, `.cache/`, and `.data/` remain at the repository root. The legacy overlay's `RAG_ROOT` continues to mean the repository root. Their contents are ignored and are not moved or published as source. GPU model caches under the user's home also retain their existing paths.
