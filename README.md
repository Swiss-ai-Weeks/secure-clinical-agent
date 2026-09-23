# Secure clinical agent (Patient360)

Patient360 combines a clinical frontend with backend deployment configuration and a planned synthetic-data ingestion pipeline.

| Path | Purpose |
| --- | --- |
| [frontend/](frontend/) | Vue application, mock data, and frontend tests |
| [backend/](backend/) | Backend deployment, ingestion, operational documentation, and examples |
| [backend/deploy/patient360/](backend/deploy/patient360/) | Patient360 stores, local model services, SQL, and store initialization |
| [backend/ingestion/](backend/ingestion/) | Reproducible Synthea source worker, tests, research, and remaining pipeline plan |
| [docs/](docs/) | Shared clinical requirements, taxonomy, roles, and architecture |
| [.scratch/ingestion-pipeline/map.md](.scratch/ingestion-pipeline/map.md) | Ingestion decision map and linked local issues |

## Frontend

```bash
cd frontend
npm ci
npm run dev
```

See [the frontend README](frontend/README.md) for development and testing instructions. The frontend connects to the backend through `/api`; mock data is also available for tests.

For the running NemoClaw deployment, UI address, and agent reliability checks, see [NemoClaw verification](docs/NEMOCLAW-VERIFICATION.md).

## Backend

Start with [the backend guide](backend/README.md). From the repository root, prepare and validate the Patient360 configuration:

```bash
cp backend/deploy/patient360/.env.example backend/deploy/patient360/.env
# Edit the local .env file with your store credentials and NGC_API_KEY.
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml config --quiet
```

The backend guide lists commands for starting stores and model services. The Compose `ingest` profile selects imaging models. The [synthetic source-worker runbook](backend/ingestion/RUNBOOK.md) covers reproducible 10/100-patient generation and the remaining sanitation, embedding, and store-publication stages.

Patient360 uses PostgreSQL for structured FHIR data and Qdrant for note chunks. The separate NVIDIA hybrid RAG overlay lives in [backend/deploy/](backend/deploy/) and currently selects Elasticsearch with hosted answer generation. Its [local migration plan](backend/docs/SELF-HOSTED-PLAN.md) and earlier operational records are preserved under `backend/docs/`; the launcher scripts they describe are not present in this checkout.
