# Resume ingestion: structured seed to authorized vector search

Session handoff updated 2026-09-18. Branch: `ingestion-pipeline`. The user requested sharing the synthetic `.data` snapshot on 2026-09-18. A checkout includes the selected datasets and registry snapshot but does not populate PostgreSQL or Qdrant; see [.data/README.md](../../.data/README.md).

## Completed and verified

- The pinned [source worker](worker.py) produces reproducible Synthea v4.0.0 FHIR and linked raw notes: 10 smoke patients/500 notes and 100 seed patients/4,645 notes. Raw batches remain immutable, hashed and restricted.
- The user approved all three [FHIR projection and update policies](../../.scratch/ingestion-pipeline/issues/05-fhir-projection.md#answer): strict projection/missing values, stable upserts with removals rejected, and reviewed fixture sensitivity labels that block unknown codes.
- [Structured ingestion](structured.py) implements persistent opaque identities, source provenance, code-aware nested projection, versioned prepared artifacts, and atomic PostgreSQL loads using the existing worker role. Patient data retains birth year only; non-patient source upsert IDs remain temporarily internal.
- Smoke was committed and replayed before seed. The committed seed contains **100 patients, 4,645 encounters, 3,579 conditions and 70,843 Observation rows**, including components. See [structured validation](structured-validation.md) for replay, relationship and clinical-example evidence.
- All **49 automated tests pass**, including six live PostgreSQL tests that roll their fixture rows back. Source generation previously passed independent reproducibility checks; see [source validation](source-worker-validation.md).
- PostgreSQL uses main's initialized `clinical`, `identity`, and `audit` schemas. No database reset, schema migration or privilege expansion was needed for these structured loads; [schema integration](schema-integration.md) records the earlier authorized bootstrap.

## Where the data and state live

| Artifact | Local directory below repository root |
| --- | --- |
| Smoke source | `.data/ingestion/fb8bc7f697698fe7a37ca1a0a37a08e9d9ff12409c71bdaea8cf9f8888c960e4/` |
| Seed source | `.data/ingestion/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36/` |
| Persistent identity/provenance | `.data/identity/registry.sqlite` |
| Versioned prepared artifacts | `.data/prepared/<projection-id>/` |
| Evaluation fixture artifacts | `.data/evaluation/<corpus-id>/` |
| Evaluation fixture evidence | `.data/evaluation-validation-20260918/` |
| Committed-load execution evidence | `.data/structured-acceptance-20260918/` |
| Earlier independent source run | `.data/runbook-_iu276uq/` |

Each source batch contains `manifest.json`, restricted `generator.log`, source FHIR bundles and `artifacts/raw-notes.jsonl`. Prepared manifests record source and policy digests, counts and exclusions; separate load receipts distinguish committed loads from dry runs. The user-approved synthetic snapshots are now tracked in this branch. PostgreSQL backups containing credential hashes, locks and debug logs remain local and ignored. Restore owner-only permissions after checkout as described in [.data/README.md](../../.data/README.md).

**Preserve and back up the registry.** Source regeneration cannot recreate its random opaque keys. On another machine, restore the registry to retain patient identities; do not initialize a replacement for an existing cohort. Follow the [runbook](RUNBOOK.md#structured-preparation-and-postgresql).

## Current boundary

Structured records are loaded into PostgreSQL. Raw notes remain unsanitized; `clinical.notes` is empty. Presidio, chunking, embeddings, Qdrant writing, seeded grants, the cross-store publication gate and authenticated retrieval are not implemented. `published: false` records this incomplete pipeline state; it is not itself a database read gate.

Main commit `07a308b` was merged into this branch, adding PostgreSQL-backed OpenFGA configuration, bootstrap and model/demo tuples. This merge does not migrate or redeploy the running services or implement the ingestion access adapter. The 2026-09-17 service inspection found Qdrant ready and the configured embedding endpoint on port 8001 unreachable. Recheck these when starting the corresponding stage. The maintained deployment is [backend/deploy/patient360/compose.yaml](../deploy/patient360/compose.yaml); its `ingest` profile selects imaging services, not this worker.

## Next decision: note de-identification and chunk boundaries

The [note-generation/evaluation decision](../../.scratch/ingestion-pipeline/issues/06-note-generation-contract.md#answer) is resolved. Eight local attack variants and three unchanged controls are implemented; see [fixture validation](evaluation-validation.md). They remain raw, unsanitized and unpublished, and security evaluation is not run. Continue with [Choose note de-identification and chunk boundaries](../../.scratch/ingestion-pipeline/issues/07-deid-and-chunking.md): recognizers, replacements, narrative age/date handling, canary validation, quarantine behavior and chunking. Existing Synthea template notes and the cohort remain approved.

1. Reuse the registry's patient/document identities and restricted encounter provenance. Preserve full raw notes unchanged and write versioned sanitized artifacts separately.
2. Preserve birth-year-only demographics and synthetic clinical event dates. Keep raw source IDs out of note enrichment, embeddings, application citations and ordinary logs. [Move source resource identifiers into restricted provenance](../../.scratch/ingestion-pipeline/issues/12-restrict-source-resource-identifiers.md) remains the follow-up for temporary clinical upsert IDs.
3. Pin Presidio/NLP/recognizer versions. Sanitize whole notes before chunking, validate planted identifier canaries, and quarantine failed/ambiguous results. The structured dictionary does not sanitize arbitrary narrative.
4. Preserve the three approved [clinical demonstrations](clinical-demo-examples.md). Their measurements are structured Observation evidence and need separate citations from note narrative. Keep historical pneumonia marked resolved. Authorized/unauthorized/revoked-access checks remain to implement.
5. Keep intentional prompt-injection fixtures separate from the clinical seed. Eight variants and three controls now exist in restricted `.data/evaluation/`; the same future sanitization and authorization rules apply, with dedicated test storage. LLM rewriting is not implemented.

Do not index `raw-notes.jsonl` directly.

## Remaining storage and retrieval stages

| Stage | Concrete work | Evidence required before moving on |
| --- | --- | --- |
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
RUN_STRUCTURED_POSTGRES_TESTS=1 python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
python3 backend/ingestion/worker.py verify .data/ingestion/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36
docker ps -a --filter label=com.docker.compose.project=patient360
```

Suggested continuation request:

> Read backend/ingestion/NEXT-STEPS.md and the decision map. The structured 100-patient seed is loaded and checked. The eight-attack evaluation corpus is also created and checked. Continue with the de-identification/chunking decision, then implement sanitized notes using the existing stable identities. Preserve raw artifacts, registry state and loaded stores. Do not report vector ingestion or retrieval complete until real model/store and authorization checks pass.

Use the [ordered implementation backlog](issues.md) and [decision map](../../.scratch/ingestion-pipeline/map.md) to record progress. GitHub implementation issues have not been closed by this checkpoint; preserve incomplete downstream acceptance criteria.
