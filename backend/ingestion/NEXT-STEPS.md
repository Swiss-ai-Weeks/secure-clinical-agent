# Resume ingestion: source data to authorized vector search

Session handoff recorded 2026-09-17. Branch: `ingestion-pipeline`. Start here after reopening the repository. Publishing this branch publishes the worker, tests, and documentation; it does **not** publish patient data into PostgreSQL or Qdrant.

## Completed and verified

- [Source worker](worker.py) runs official Synthea v4.0.0 with pinned artifact/runtime digests, seeds, dates, geography, and configuration.
- The approved profiles are **10 smoke patients** and **100 seed patients**.
- The smoke batch contains 500 linked notes; the seed contains 4,645. Notes are extracted from FHIR DocumentReference and keep patient/encounter/document lineage.
- Raw output is hashed, counted, and validated before `source_ready`. Reruns verify and reuse completed batches. Failed attempts remain separate; concurrent jobs using one output root are rejected.
- All 18 automated tests passed. The runbook was executed again: both existing batches verified, a new independent smoke generation matched exactly, and the tests passed again.
- Synthea generates template-based clinical notes. LLM rewriting and intentional prompt-injection fixtures have not been implemented.
- PostgreSQL was rebuilt with the user's authorization after backup, using main's current `clinical`, `identity`, and `audit` schemas. Role logins and selected constraints/permissions passed runtime checks; the clinical seed is not loaded. See [schema integration evidence](schema-integration.md).

See [validation evidence](source-worker-validation.md), [the inspected source contract](research/synthea-generator-contract.md), and [operating commands](RUNBOOK.md).

## Where the data is

On the current NVIDIA server, the verified batches are:

| Profile | Local directory below repository root |
| --- | --- |
| Smoke | `.data/ingestion/fb8bc7f697698fe7a37ca1a0a37a08e9d9ff12409c71bdaea8cf9f8888c960e4/` |
| Seed | `.data/ingestion/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36/` |

Each contains `manifest.json`, restricted `generator.log`, `artifacts/source/fhir/*.json`, and `artifacts/raw-notes.jsonl`. The latest execution record is `.data/runbook-_iu276uq/execution.json`; its fresh smoke output is in the sibling `independent-smoke/` directory.

These artifacts are ignored and **not pushed to GitHub**. On another machine, run the worker to recreate them. Recorded IDs apply to the current worker/config; changing the worker or configuration changes the batch ID. Use the path returned by the command rather than assuming these IDs always apply.

## Current boundary

The pipeline stops at `source_ready`, with `sanitized: false` and `published: false`. There is no opaque identity adapter, Presidio adapter, PostgreSQL ingestion, chunker, embedding client, Qdrant writer, grant seeding, publication gate, or search interface yet. A successful source run does not populate existing stores.

The last server inspection found PostgreSQL and Qdrant running, Qdrant `/readyz` returning HTTP 200, and the configured embedding endpoint at port 8001 unreachable. Both GPUs were idle at that inspection. Recheck at the start of the next session; these are observations, not permanent guarantees. Container labels retain the old Compose file location; the maintained definition is [backend/deploy/patient360/compose.yaml](../deploy/patient360/compose.yaml). Its `ingest` profile selects imaging services, not this worker.

## Immediate next step: safe projection and sanitized artifacts

Main's [FHIR resource plan](../../docs/Patient360-FHIR-Resource-Plan.md) and expanded SQL schema are merged, and the user reconciled the three differences: birth year only, temporary raw non-patient source resource IDs, and a backed-up demo database-volume replacement. The new database is initialized and validated; read the [schema integration checkpoint](schema-integration.md) for evidence and remaining adapter work.

Begin with [Choose the FHIR-to-PostgreSQL projection and update rules](../../.scratch/ingestion-pipeline/issues/05-fhir-projection.md), the next unblocked decision. Generator identification, [cohort scope](../../.scratch/ingestion-pipeline/issues/03-cohort-and-success.md#answer), and [identity/provenance](../../.scratch/ingestion-pipeline/issues/04-identity-and-provenance.md#answer) are resolved. Detailed sanitization and access contracts remain open; approved designs are not implemented adapters.

1. Preserve the approved cohort and demonstration scope recorded in the [cohort resolution](../../.scratch/ingestion-pipeline/issues/03-cohort-and-success.md#answer). A small, separately labelled synthetic prompt-injection evaluation corpus is approved, kept separate from the clinical seed; it is not implemented.

   [Three verified clinical demonstration examples](clinical-demo-examples.md) are approved: diabetes self-management, hypertension education, and historical pneumonia, with authorized, unauthorized, and revoked-access checks. Each links a source diagnosis, measured observation, and encounter note. Measurements occur in structured Observations rather than these notes; demonstrate and cite the two evidence sources separately.
2. Apply the amended identity contract: stable opaque patient keys, birth year only, preserved clinical event dates, and temporary raw non-patient `source_id` upsert keys within the agreed source namespace. Keep full DOB out of prepared records and note/embedding payloads. Resolve nested safe projection, labels, coding/components, and updates/deletions. [Move source resource identifiers into restricted provenance](../../.scratch/ingestion-pipeline/issues/12-restrict-source-resource-identifiers.md) records the required follow-up.
3. Implement a preparation stage that consumes a **verified** source batch. Preserve the raw batch unchanged; write separate versioned prepared artifacts and a stage manifest. Exact filenames and the CLI are to be agreed during implementation, not existing commands.
4. Pin Presidio/NLP/recognizer versions and the replacement policy. Sanitize full notes before chunking, validate planted synthetic identifier canaries, and quarantine failed or ambiguous results. Define an explicit structured-field projection; raw FHIR must not be copied into unrestricted PostgreSQL JSONB.
5. Test stable identity, cross-patient rejection, source lineage, sanitization failure handling, clinical-value preservation, and the temporary identifier boundary: source resource IDs only in approved internal upsert fields/restricted provenance, never in embeddings, application citations, or ordinary logs. Patient source identity remains restricted.

Do not skip this boundary to index `raw-notes.jsonl` directly.

## Then implement storage and retrieval in order

| Stage | Concrete work | Evidence required before moving on |
| --- | --- | --- |
| Structured storage | Implement the agreed safe Patient/Condition/Observation projection against the initialized main schema, including required Encounter linkage and stable upserts. | Correct patient links, codes/values/units, and replay without duplicates; defined changed/deleted-source behavior. The worker must not reset volumes on retry. |
| Grants and access contract | Resolve care-team/consent semantics, install the OpenFGA model, persist store/model IDs, seed grants, and define mandatory patient/security metadata. | Allow, deny, missing-metadata, revocation, and grant-store restart behavior. Memory-backed grants must not silently disappear while reads stay enabled. |
| Embedding readiness | Bring up the configured embedding service when implementing this stage. Inspect actual model ID, image digest, serving profile, tokenizer, and token limit. Test passage and query modes. | Finite vectors, correct response indices, verified dimensions, and explicit oversize-input rejection. The existing 2048-dimensional Cosine collection definition is configuration intent until checked against the live services. |
| Chunking and Qdrant writes | Chunk only sanitized notes using the verified tokenizer. Assign deterministic UUID point IDs and retain sanitized text, offsets, patient/document/source lineage, model/policy versions, and agreed ACL metadata. Validate/create the required collection indexes and cache validated embeddings for retries. | Stable point counts on replay, no raw identifiers in embedding requests/payloads, rejection of incompatible collections, and explicit replacement/deletion rules. Do not drop an existing collection to fix incompatibility. |
| Batch publication | Add stage checkpoints and a trusted read gate. Verify PostgreSQL, Qdrant, and grants before a batch becomes queryable. | Interrupted/partial writes remain invisible; retries resume without duplication. A payload flag alone does not implement authorization or a cross-store publication gate. |
| Search queries | Build a backend search boundary that accepts an authenticated caller and query, resolves current grants, embeds in query mode with the compatible model, and applies mandatory scope/publication filters before returning any note text. | Authorized relevant results with citations; denial for unauthorized/revoked callers; no text exposure before authorization; empty results and dependency failures handled explicitly. |

The initial search result contract should include sanitized snippet, patient/document/chunk identifiers, score, and source citation. Caller-controlled patient filters may narrow authorized scope but must never expand it. Test retrieval with different principals over the same query and with a revoked grant; expected matches should come from source-grounded clinical examples. Keep reranking as a later stage over already-authorized candidates.

This is the proposed search behavior, **not an implemented endpoint or command**. Choose the actual public API/CLI and tests when implementing the retrieval boundary. The existing frontend uses its own mock services; connecting it to real search is a separate integration step.

## Start a new session

Run from the repository root:

```bash
git status --short --branch
python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
python3 backend/ingestion/worker.py run --profile smoke
docker ps -a --filter label=com.docker.compose.project=patient360
```

Suggested continuation request:

> Read backend/ingestion/NEXT-STEPS.md and the linked decision tickets. Continue from the verified Synthea source worker toward sanitized, authorized vector search. Cohort, clinical examples, and identity/provenance are approved. Start with the safe FHIR projection and update-rules decision, then resolve the remaining note/de-identification prerequisites before implementing and testing preparation. Preserve source artifacts and existing services. Do not report vector ingestion or retrieval complete until real model/store and authorization checks pass.

Use the [ordered implementation backlog](issues.md) and [decision map](../../.scratch/ingestion-pipeline/map.md) to record progress. GitHub implementation issues were not closed during this session; keep incomplete acceptance criteria visible. The user subsequently requested all pending repository changes be published to `ingestion-pipeline`, including the product documents, learning assets, and document moves. Ignored source datasets and restricted local evidence remain local.
