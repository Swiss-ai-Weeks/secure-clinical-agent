# Adversarial fixture validation

Recorded 2026-09-18 after approval of [Define clinically linked synthetic-note generation](../../.scratch/ingestion-pipeline/issues/06-note-generation-contract.md#answer).

## Created and checked

The [evaluation builder](evaluation.py) created **eight attack variants, three unchanged controls and eight case specifications** from the approved diabetes, hypertension and historical-pneumonia examples. Two variants cover each category: authority overrides, patient-access bypass, export attempts and answer/citation manipulation.

- Original source narratives remain byte-for-byte unchanged within each variant; the attack is a separately tracked appended passage.
- All 11 evaluation documents have distinct deterministic identities, separate from their clinical source identities. Patient, encounter and source-document links match existing registry mappings.
- Historical source status is retained. Missing mappings, broken patient/encounter links, unapproved selection, mismatched source hashes and corrupted completed output fail the build.
- The completed corpus was replayed, then built independently. All artifact and manifest bytes matched.
- The clinical registry file hash and full PostgreSQL row snapshots were unchanged. `clinical.notes` remains empty. The builder contains no model, email, export or store writer.
- Source/structured ingestion rejects the evaluation-stage manifest as an ordinary clinical source batch. Output paths cannot overlap the source, registry or default prepared clinical storage.
- All **49 tests pass**, including nine new evaluation tests and the existing six opt-in live PostgreSQL checks. The live checks roll back their own fixture rows.

Restricted corpus on this server:

`.data/evaluation/cbac6c5c174a26e02e960cc2f5766ae232c571a697f7c8a3a1b1424cd3c2fce7/`

The [local execution record](../../.data/evaluation-validation-20260918/execution.json) records the initial build, replay, independent build and invariance checks. Its [driver](../../.data/evaluation-validation-20260918/run.py) holds the runtime assertions. These ignored files are local evidence, not repository assets available in a fresh checkout.

## What has not been tested yet

The corpus is `evaluation_source_ready`, **unsanitized, unpublished**, and explicitly marked `security_evaluation: not_run`. Case specifications require authorized, unauthorized and revoked-access scenarios, useful unchanged-control responses, correct clinical citations, and no instruction-induced export calls. These are expected outcomes, not observed results.

The builder proves source lineage, fixture identity, local output separation and reproducibility. It does not implement Presidio, a quarantine policy, vector storage isolation, authorization enforcement, retrieval, model calls or an end-to-end security evaluator. Export URLs and addresses use reserved `.invalid` examples; future execution must use mocks rather than send messages or records.

Continue with [Choose note de-identification and chunk boundaries](../../.scratch/ingestion-pipeline/issues/07-deid-and-chunking.md), then the existing access/vector/publication decisions. Preserve the approved distinction between sanitizing identifiers and intentionally retaining attack instructions inside isolated evaluation text.

## Reproduce

The [runbook](RUNBOOK.md#isolated-adversarial-evaluation-fixtures) provides the actual build command and required restricted source selection/registry state.

```bash
python3 -m unittest discover -s backend/ingestion/tests -p test_evaluation.py -v
RUN_STRUCTURED_POSTGRES_TESTS=1 python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
```
