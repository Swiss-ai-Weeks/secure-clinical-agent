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
