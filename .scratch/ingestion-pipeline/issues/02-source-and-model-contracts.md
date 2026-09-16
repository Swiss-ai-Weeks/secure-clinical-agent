# Verify Synthea, Presidio, and embedding integration contracts

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: research
Label: wayfinder:research
Status: resolved
Assignee: root/research_contracts
Blocked by: none

## Question

What do primary sources establish about reproducible Synthea FHIR R4 export and reference handling, Presidio detection/anonymization limits, and the configured llama-nemotron-embed-vl-1b-v2 embedding contract (model ID, passage/query modes, token limit, vector dimensions)? Which Qdrant 1.13.6 payload/index/filter capabilities support patient-scoped note chunks, and what must be checked against the running service before implementation?

Distinguish published facts, local configuration, and runtime facts not yet verified. Investigate the services configured in backend/deploy/patient360/compose.yaml, not the separate Elasticsearch RAG overlay. Include evidence relevant to a later reranker, without selecting or deploying one. Capture findings as a linked Markdown asset on a research/source-model-contracts branch. Do not assume the user's pending note-generator project or API.

## Answer (resolution comment, 2026-09-16)

Published contracts and remaining runtime checks are captured in [Patient360 ingestion: source and model contracts](../../../backend/ingestion/research/source-model-contracts.md). Synthea exports FHIR R4 with explicit generation/export controls; bundle references require identity-aware resolution. Presidio needs a versioned evaluation and identity policy, not an assumption of complete anonymization. The configured VL embedding model uses 2048-dimensional output, while NIM 2.2 documents a default 2048-token profile, distinct from the model card's 10240-token evaluation. The deployment's actual limit remains unverified. Qdrant v1.13.6 supports payload indexes and filtered queries, but ACL enforcement must remain in the trusted authorization/retrieval boundary. The future reranker receives only authorized, sanitized candidates.

Research context: branch `research/source-model-contracts`, commit `e89d8998b560612f23db052cc7a57447a33d1987`, worktree `/tmp/patient360-ingestion-research`. Only the research asset is committed there; a relocated copy with updated repository references is available in the ingestion planning checkout. No service execution, runtime checks, generator selection, or HITL product-policy decisions were performed.
