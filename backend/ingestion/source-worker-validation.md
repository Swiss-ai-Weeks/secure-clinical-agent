# Source-worker validation — 2026-09-17

Implementation on `ingestion-pipeline`, built on commit `5aabb8c`. This evidence accompanies the source-worker publication; generated datasets remain local and ignored. Source contract: [Synthea inspection](research/synthea-generator-contract.md); configuration: [synthea.json](config/synthea.json). Continue from [the session handoff](NEXT-STEPS.md).

## Real generation results

| Profile | Patients | Clinical notes | Conditions | Observations | Batch ID |
| --- | ---: | ---: | ---: | ---: | --- |
| Smoke | 10 | 500 | 388 | 6,598 | `fb8bc7f697698fe7a37ca1a0a37a08e9d9ff12409c71bdaea8cf9f8888c960e4` |
| Seed | 100 | 4,645 | 3,579 | 50,363 | `71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36` |

These are observed counts from generated FHIR, not requested or estimated counts. Each note resolves to an actual DocumentReference, patient, and encounter in its bundle. Historical notes are retained and DiagnosticReport duplicates are excluded. Generated datasets and raw note text are restricted local artifacts, not committed source fixtures.

The smoke batch was generated independently under `.data/ingestion/` and `.data/ingestion-repeat/`. `worker.py compare` returned `independent_runs_equal: true`: the manifests, raw FHIR artifact hashes, and extracted note hashes matched exactly. Repeating the smoke command returned `reused: true` after integrity and lineage verification. This proves repeatability for the tested pinned runtime/configuration; it does not prove arbitrary configurations or future embedding results are bitwise identical.

The seed profile completed once with the expected 100 distinct patients. A second independent 100-patient run was not performed. One attempted simultaneous invocation was rejected with `worker_already_running`; rerunning after the active verification finished succeeded.

The runbook was subsequently executed again at the user's request. Both completed profiles passed explicit verification, another fresh smoke generation matched the existing smoke batch exactly, and all 18 automated tests passed. The local execution report is `.data/runbook-_iu276uq/execution.json`; the independent source artifacts are retained below that directory. This report and the raw datasets are deliberately excluded from Git publication.

## Automated checks

`python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v`: **18 tests passed**. They cover CLI behavior for raw-source counts/lineage, historical notes and duplicate representations, completed-batch reuse, independent artifact equality, changed-config identity, corrupt artifacts, invalid source-stage claims, concurrent jobs, process failure/retry, count mismatch, JAR integrity, immutable runtime configuration, fixed dates, unresolved/ambiguous references, invalid encounter targets, duplicate resource IDs, missing notes, and invalid attachment encodings/media.

The executable tests use a fake Docker process at the external boundary. The real Synthea runs above independently verify the actual pinned generator integration. No database or embedding adapter exists in this slice; no test claims that those stages pass.

## Remaining runtime evidence

- Qdrant `/readyz`: HTTP 200. Collection dimensions, indexes, policy enforcement, and data writes were not tested.
- Nemotron embedding `/v1/models` at loopback port 8001: unreachable at inspection time. No passage/query request was made, and no GPU profile/token limit was verified.
- PostgreSQL, OpenFGA, and publication: unchanged. No ingestion records or grants were written.
- Presidio, opaque identity mapping, clinical fidelity, and authorization acceptance: still required before downstream ingestion/publication.

Both generated batches explicitly report `source_ready`, `synthetic: true`, `sanitized: false`, and `published: false`. The [runbook](RUNBOOK.md) distinguishes the completed source stage from the steps required to reach the planned vector database.
