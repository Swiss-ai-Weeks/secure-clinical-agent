# Define acceptance evidence and the implementation handoff

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: 10

## Question

What checks and measured results prove the selected design is ready to implement and subsequently prove that its first seed succeeded?

Specify a tiny reproducible fixture and the agreed full seed, expected patient/resource/note/chunk counts, consistent linkage, FHIR code/unit/date preservation, explicit excluded/quarantined counts, and clinical consistency checks. Require identifier-canary checks at embedding inputs, persisted payloads/JSON, and logs; allow/deny/revocation checks before reranking or generation; repeat-run idempotency; interruption/restart recovery; grant reseeding/persistence; and incompatible-dimension rejection.

Define basic retrieval relevance examples over synthetic ground truth and a later reranker comparison boundary without adding a reranker now. Confirm an ordered implementation backlog and acceptance commands after preceding decisions close. Planning completion means an approved implementable spec with no remaining prerequisite decisions; it does not claim the databases are populated or the pipeline is running.

## Comments

### Approved demonstration input — 2026-09-17

[Choose the first cohort and ingestion success criteria](03-cohort-and-success.md#answer) is resolved. Use its approved [clinical demonstration examples](../../../backend/ingestion/clinical-demo-examples.md) and access expectations as inputs to the eventual executable acceptance checks. The examples distinguish note narrative from structured measurements and historical from current conditions. Exact ranking thresholds, sanitized fixture mappings, and runtime commands remain to be specified here after the blocking contracts resolve; the source-evidence checks are not retrieval tests.

### Approved attack cases — 2026-09-18

The [note-generation/evaluation resolution](06-note-generation-contract.md#answer) fixes eight cases and unchanged controls, with expected authority, patient-access, export and answer/citation outcomes. [Fixture validation](../../../backend/ingestion/evaluation-validation.md) verifies local lineage/reproducibility and unchanged clinical stores. All end-to-end cases remain `not_run`; require the real sanitizer, authorization and retrieval/generation path before recording resistance or access outcomes.
