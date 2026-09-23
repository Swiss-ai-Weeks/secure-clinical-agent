# Resume ingestion: structured seed to authorized vector search

Session handoff updated 2026-09-18 after implementing tokenizer-aware chunk preparation and passage embeddings. Current checkout: `main`, with concurrent application/frontend work present; preserve it. Earlier source/structured implementation evidence below came from `ingestion-pipeline` and was not rerun during this decision update. The user requested sharing the synthetic `.data` snapshot on 2026-09-18. A checkout includes the selected datasets and registry snapshot but does not populate PostgreSQL or Qdrant; see [.data/README.md](../../.data/README.md).

## Completed and verified

- The pinned [source worker](worker.py) produces reproducible Synthea v4.0.0 FHIR and linked raw notes: 10 smoke patients/500 notes and 100 seed patients/4,645 notes. Raw batches remain immutable, hashed and restricted.
- The user approved all three [FHIR projection and update policies](../../.scratch/ingestion-pipeline/issues/05-fhir-projection.md#answer): strict projection/missing values, stable upserts with removals rejected, and reviewed fixture sensitivity labels that block unknown codes.
- [Structured ingestion](structured.py) implements persistent opaque identities, source provenance, code-aware nested projection, versioned prepared artifacts, and atomic PostgreSQL loads using the existing worker role. Patient data retains birth year only; non-patient source upsert IDs remain temporarily internal.
- Smoke was committed and replayed before seed. The committed seed contains **100 patients, 4,645 encounters, 3,579 conditions and 70,843 Observation rows**, including components. See [structured validation](structured-validation.md) for replay, relationship and clinical-example evidence.
- The earlier validation recorded **49 passing automated tests**, including six live PostgreSQL tests that roll their fixture rows back. This is historical evidence, not a fresh test run against the changed checkout. Source generation previously passed independent reproducibility checks; see [source validation](source-worker-validation.md).
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

Structured seed loads have prior recorded evidence. The embedding NIM is running and passed harmless passage/query, dimension/index and oversize-rejection checks; see [embedding readiness](embedding-readiness.md). The note worker now uses the pinned tokenizer, exact heading/body offsets and validated passage responses; it saves restricted unpublished artifacts. See [vector preparation validation](vector-preparation-validation.md). The application upload helper is separate and was not migrated in this step. The existing sanitizer still needs full approved-policy validation. Live cross-store publication, replay and authorized retrieval acceptance remain unproved. The earlier empty-note-store snapshot must be rechecked before any new writes; it is not a current count. A `published` flag alone is not a trusted read gate.

Main commit `07a308b` was merged into this branch, adding PostgreSQL-backed OpenFGA configuration, bootstrap and model/demo tuples. This merge does not migrate or redeploy the running services or implement the ingestion access adapter. The 2026-09-17 service inspection found Qdrant ready and the configured embedding endpoint on port 8001 unreachable. Recheck these when starting the corresponding stage. The maintained deployment is [backend/deploy/patient360/compose.yaml](../deploy/patient360/compose.yaml); its `ingest` profile selects imaging services, not this worker.

## Next implementation: versioned vector writes and trusted eligibility

The user reconfirmed section-aware 512/64 model-token chunking, exact sanitized citations, contract-specific clinical/evaluation collections and staged document versions. The [acceptance decision](../../.scratch/ingestion-pipeline/issues/11-acceptance-and-handoff.md#answer) is now resolved: prove the three clinical examples first, require their supporting passages within the top five authorized chunks, then expand to smoke and seed. Validated notes may become eligible while other notes remain quarantined, but report the run as partial and fail baseline acceptance for unexpected quarantines. Policy approval does not establish implementation success.

The [embedding and Qdrant contract](../../.scratch/ingestion-pipeline/issues/09-vector-contract.md#answer) is resolved. It owns exact input construction, heading/body citations, contract and document identities, deterministic point IDs, payload fields/indexes, and version eligibility. [Harmless tokenizer probes](embedding-readiness.md#tokenizer-boundary-and-bounded-batch-verification--2026-09-18) verified complete formatted token counts, acceptance at 4,096 tokens and rejection at 4,097 in both modes, plus passage batches up to 32. Start with eight chunks per sequential request; no server maximum is claimed.

Tokenizer-aware section chunking and the response-validating passage embedding adapter are implemented and tested, including a harmless live NIM check. Each split chunk carries its sanitized source heading within the 512-token budget; heading and body keep separate exact citation offsets. The worker refuses publication: local preparation IDs are not final document/publication/point identities. Next implement versioned Qdrant writes and trusted publication/authorization before the approved pilot; use the [runbook](RUNBOOK.md#unpublished-note-preparation-and-embedding) for the completed stage. The recorded concurrent Compose changes regressed digest pinning, compilation-cache mounting and Docker's shell-based health check; restore those known fixes before deployment acceptance while preserving other sessions' work. No seed notes were embedded or indexed during this implementation validation.

The [note-generation/evaluation decision](../../.scratch/ingestion-pipeline/issues/06-note-generation-contract.md#answer) remains resolved. Eight local attack variants and three unchanged controls have fixture evidence; see [fixture validation](evaluation-validation.md). The real sanitizer/retrieval/generation security evaluation still needs recorded outcomes.

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
| Embedding readiness | Service probes and worker input/response validation passed; reconcile recorded deployment drift and bind full model asset identity before store publication. | [Recorded probes](embedding-readiness.md) verified complete formatted counts, finite 2048-dimensional vectors, response indices and 4096/4097 acceptance/rejection. Full pipeline acceptance remains pending. |
| Versioned Qdrant writes | Reuse the implemented sanitized chunk/embedding artifacts. Assign deterministic UUID point IDs and retain sanitized text, offsets, patient/document/source lineage, model/policy versions, and agreed ACL metadata. Validate/create the required collection indexes and cache validated embeddings for retries. | Stable point counts on replay, no raw identifiers in embedding requests/payloads, rejection of incompatible collections, and explicit replacement/deletion rules. Do not drop an existing collection to fix incompatibility. |
| Batch publication | Add stage checkpoints and a trusted read gate. Verify PostgreSQL, Qdrant, and grants before a batch becomes queryable. | Interrupted/partial writes remain invisible; retries resume without duplication. A payload flag alone does not implement authorization or a cross-store publication gate. |
| Search queries | Build a backend search boundary that accepts an authenticated caller and query, resolves current grants, embeds in query mode with the compatible model, and applies mandatory scope/publication filters before returning any note text. | Authorized relevant results with citations; denial for unauthorized/revoked callers; no text exposure before authorization; empty results and dependency failures handled explicitly. |

The initial search result contract should include sanitized snippet, patient/document/chunk identifiers, score, and source citation. Caller-controlled patient filters may narrow authorized scope but must never expand it. Test retrieval with different principals over the same query and with a revoked grant; expected matches should come from source-grounded clinical examples. Keep reranking as a later stage over already-authorized candidates.

This is the proposed search behavior, **not an implemented endpoint or command**. Choose the actual public API/CLI and tests when implementing the retrieval boundary. The existing frontend uses its own mock services; connecting it to real search is a separate integration step.

## Start a new session

Run from the repository root:

```bash
git status --short --branch
# Install requirements-vector.txt in an isolated Python environment first (see RUNBOOK.md).
RUN_STRUCTURED_POSTGRES_TESTS=1 python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
python3 backend/ingestion/worker.py verify .data/ingestion/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36
docker ps -a --filter label=com.docker.compose.project=patient360
```

Suggested continuation request:

> Read backend/ingestion/NEXT-STEPS.md, vector-preparation-validation.md and the resolved embedding contract. Continue from the implemented unpublished chunk/embedding stage with versioned Qdrant writes and a trusted eligibility ledger. Follow the contract's versioned identities, payload/index requirements and publication/access boundaries before writing or exposing seed content. Reconcile recorded deployment drift without overwriting concurrent work. The accepted three-example pilot precedes smoke and seed; preserve raw artifacts, registry state and loaded stores. Do not equate model probes with passed end-to-end ingestion or access acceptance.

Use the [ordered implementation backlog](issues.md) and [decision map](../../.scratch/ingestion-pipeline/map.md) to record progress. GitHub implementation issues have not been closed by this checkpoint; preserve incomplete downstream acceptance criteria.
