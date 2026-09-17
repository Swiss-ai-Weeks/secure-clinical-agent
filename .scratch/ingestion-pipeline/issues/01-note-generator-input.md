# Identify the synthetic-note generator and obtain its API contract

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: task
Label: wayfinder:task
Status: resolved
Assignee: Codex
Blocked by: none

## Question

Which project/API will generate the synthetic notes, and can its contract and a synthetic example be inspected before choosing the adapter?

Human input needed: provide the project/repository URL (and API documentation if separate). Do not paste credentials. If private access is required, identify the approved access mechanism. The investigator should then inspect request/response schemas, local versus hosted execution, licensing, reproducibility controls, identifiers, output formats, limits, and failures. No live generation is needed for this decision prerequisite.

The user supplied https://github.com/synthetichealth/synthea on 2026-09-17 and authorized worker implementation. Inspect its actual FHIR and narrative export interfaces before defining the source adapter. Recommended input is the same Synthea patient/encounter history that feeds PostgreSQL, with provenance preserved. Resolution records the actual contract and example location, not an invented API.

## Answer — 2026-09-17

Use the supplied Synthea repository's official v4.0.0 release. The [inspected contract](../../../backend/ingestion/research/synthea-generator-contract.md) records the source revision, published JAR checksum, Apache-2.0 licensing, local Java CLI, reproducibility controls, and actual FHIR/note export formats. No hosted generator API or fabricated parameters are required.

The FHIR R4 exporter already generates English encounter notes from the same patient histories. Extract DocumentReference's base64 UTF-8 attachment once, retain patient/document/encounter references, and avoid the duplicate DiagnosticReport copy. Historical `superseded` notes are retained. Note types are upstream History and Physical / Evaluation and Plan; other clinical scope choices remain in the cohort and note-contract tickets.

The [source worker](../../../backend/ingestion/worker.py) runs the pinned JAR in a pinned network-isolated Java container, validates artifacts and linkage, and records hashes/counts. A real 10-patient sample yielded 500 notes. Two fresh runs with the same pinned contract produced equal source/note artifacts and manifests; a third invocation reused the verified batch. The restricted synthetic example is `.data/ingestion/fb8bc7f697698fe7a37ca1a0a37a08e9d9ff12409c71bdaea8cf9f8888c960e4/artifacts/`, locally ignored rather than committed. [Commands and limitations](../../../backend/ingestion/RUNBOOK.md).

This resolves generator identification and source-contract inspection only. It does not resolve clinical acceptance, identity privacy policy, Presidio validation, grants, embedding readiness, or store publication.
