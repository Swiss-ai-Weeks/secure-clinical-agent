# Patient360 backend

Backend source and deployment configuration live here, alongside the top-level `frontend/`. Run the commands below from the **repository root**.

```text
backend/
├── deploy/
│   ├── patient360/       # Compose, SQL, store initialization, environment template
│   ├── compose.hybrid.yaml
│   ├── hybrid.env       # Non-secret shell configuration for the legacy RAG overlay
│   └── blueprint.ref    # Pinned upstream NVIDIA RAG revision
├── ingestion/           # Synthea source worker, tests, research, and remaining pipeline plan
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
  -f backend/deploy/patient360/compose.yaml up -d \
  postgres openfga openfga-init qdrant qdrant-init openbao minio minio-init orthanc
```

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
| initdb, operators | `fhir_app` | superuser; bypasses every `REVOKE`, so no service uses it |

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
