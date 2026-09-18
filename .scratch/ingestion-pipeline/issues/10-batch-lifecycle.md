# Choose batch orchestration, publication, and recovery

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: none
Blocked by: 05, 06, 07, 08, 09

## Question

How will an isolated ingestion job move a batch through validation, grants, PostgreSQL, and Qdrant without exposing partially processed or unauthorized records?

Choose a minimal batch command/worker interface, manifests/checkpoints, readiness checks, stage statuses, retry and quarantine policy, and a publication/read gate that works across stores without assuming a distributed transaction. Decide visibility on partial failure, replay/resume behavior, deletion/reprocessing, and protection against duplicate notes/rows/chunks. Scope credentials/networks to the worker; it must not be invokable by the clinical agent.

Decide artifact storage and retention: the architecture shows quarantine but current MinIO initialization creates only reports and vlm-descriptions. Clarify whether local restricted batch artifacts suffice initially or quarantine storage is required. Include grant-store restart and embedding outage scenarios, sanitized logs/audit evidence, and actual readiness checks rather than relying on healthchecks that always return success.

## Answer

Locked 2026-09-18. A note becomes queryable only when Postgres `published=true` (CHECK already requires `sanitized_ref` + `deid_version`) **and** matching Qdrant points have `published=true`. Partial writes stay unpublished. `notes.py` checkpoints per note id; retries reuse deterministic point ids. Failed/ambiguous sanitization goes to MinIO `quarantine/` (bucket already created by `minio-init`) plus a local restricted failure record. Embedding outage leaves the row unpublished. The worker is CLI-only and is not a published compose port. Eval corpus never publishes into `note_chunks`.
