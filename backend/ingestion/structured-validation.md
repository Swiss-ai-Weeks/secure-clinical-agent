# Structured ingestion validation

Recorded 2026-09-18 after the user approved all three [FHIR projection and update policies](../../.scratch/ingestion-pipeline/issues/05-fhir-projection.md#answer). **Smoke and seed are committed to PostgreSQL.** This completes structured storage for the approved synthetic cohort; note sanitization, grants and authorized vector retrieval remain outside this checkpoint.

## Committed counts

| Cohort | Patients | Encounters | Conditions | Observations, including components |
| --- | ---: | ---: | ---: | ---: |
| Smoke, loaded first | 10 | 500 | 388 | 8,914 |
| Full seed, including smoke | 100 | 4,645 | 3,579 | 70,843 |

The seed added 90 patients, 4,145 encounters, 3,191 conditions and 61,929 observations. The source fixtures overlap: the database contains 100 patients, not 110. Address, race, ethnicity and language components are excluded from rows and nested JSON: 464 components in smoke and 4,108 in seed.

## Runtime acceptance

The restricted [execution record](../../.data/structured-acceptance-20260918/execution.json) preserves each committed invocation, change counts, prepared artifact paths and table snapshots. The [local validation driver](../../.data/structured-acceptance-20260918/run.py) contains the assertions. These ignored files are local evidence; they are not distributed with a fresh checkout.

- Smoke was committed only after all pre-load tests passed. Immediate replay changed zero rows, and snapshots of complete rows—including identities, citations and timestamps—were identical.
- Every load compares every staged column against PostgreSQL before committing, including codes, values, units, labels, JSON, dates and references.
- Patient/encounter joins and Observation parent links are checked independently of the importer. Excluded Observation codes and stored note rows are absent.
- Seed replay changed zero rows. Replaying smoke after seed also changed zero rows and preserved the full 100-patient seed. The original smoke subset retained its complete row snapshots, including identities, citations and timestamps.
- Loads use the existing `p360_worker` role and an atomic transaction with audit insertion. No database reset, clinical DELETE or privilege expansion occurred. Source artifacts remain immutable and are reverified during preparation.

## Clinical fidelity

An independent check uses the approved source locators, verifies source bundle hashes, resolves the registry mappings, and compares live SQL records with original measurements. See the [restricted results](../../.data/structured-acceptance-20260918/clinical-examples.json) and [validation script](../../.data/structured-acceptance-20260918/examples.py).

| Approved example | Verified live measurements | Additional checks |
| --- | --- | --- |
| Diabetes self-management | HbA1c 6.98% | Active diagnosis; matching patient, encounter and event time |
| Hypertension education | Blood pressure 143/89 mm[Hg] | Both components link to the correct panel and encounter |
| Historical pneumonia | Oxygen saturation 87.4%; respiratory rate 25.905/min | Diagnoses remain resolved; safe alternate oxygen coding preserved |

All three retain restricted document-to-encounter provenance and matching source narrative. Raw notes are neither sanitized nor loaded. These checks do not establish retrieval results, ranking, or allow/deny/revocation behavior.

## Tests and replay performance fix

All **40 tests pass**: 18 source-worker tests, 16 projection/identity tests, and six opt-in PostgreSQL integration tests. Live tests insert their own fixtures and roll them back. Coverage includes registry restart/backup/restore, identifier canaries, code-aware omissions, scalar/component fidelity, unknown codes, missing values, wrong references, labels, stable updates, rejected removals, ownership boundaries and denied worker DELETE.

The first full-seed replay exposed a staging-query performance defect: PostgreSQL chose a nested-loop anti-join and repeatedly scanned the entire unindexed Observation staging table. The removal check exceeded its 120-second statement timeout; the transaction rolled back. Unique staging-key indexes plus `ANALYZE` fixed the plan without changing the data contract or raising timeouts. A focused 70,843-row probe improved from exceeding two seconds to **0.38 seconds**. A 12,000-row importer regression exercises the real insert/replay path with a two-second per-statement budget on replay.

```bash
RUN_STRUCTURED_POSTGRES_TESTS=1 python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
```

Ordinary discovery skips the six live tests unless opted in. Live tests require the maintained PostgreSQL container and its configured worker password. The [runbook](RUNBOOK.md#structured-preparation-and-postgresql) contains prepare, load, dry-run and backup commands.

## Artifacts and recovery

Prepared output is under ignored `.data/prepared/<projection-id>/`; identity includes source batch, adapter/policy digests and registry identity. Each stage contains immutable table JSON files plus hashes, counts, exclusions and source-contract evidence in `manifest.json`. A separate `load-receipt.json` records whether the most recent operation was rolled back. The execution record preserves the full load sequence instead of relying on the latest receipt alone.

The post-seed backup `.data/identity/registry-seeded-20260918.sqlite` passed SQLite integrity checking and exact comparison of all registry tables, including document links and provenance. Preserve `.data/identity/registry.sqlite` and its backups. Regenerating source does not recreate its random opaque identities. Missing/corrupt registry state requires restoration; never reinitialize an existing cohort. The registry stores restricted source links and must not be used as an application citation payload.

Source batches retain `sanitized: false` and `published: false`. Structured loading is complete; cross-store publication and authenticated reads are not implemented. `clinical.notes` remains empty, and this stage makes no embedding or Qdrant writes.
