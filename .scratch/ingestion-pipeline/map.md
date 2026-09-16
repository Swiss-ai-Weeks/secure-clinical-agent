# Plan the Patient360 synthetic ingestion pipeline

Label: wayfinder:map
Status: active

## Destination

An implementation-ready, step-by-step specification for reproducibly seeding Patient360 with linked synthetic patients and notes: Synthea FHIR projected into PostgreSQL, and de-identified, embedded, ACL-tagged note chunks published to Qdrant. Completion requires resolved data, identity, authorization, lifecycle, and acceptance contracts; execution is a subsequent effort.

## Notes

- User requests planning and issues on a new ingestion-pipeline branch. This map is planning-only; do not deploy services, generate datasets, or implement the worker while charting.
- Canonical tracker is the existing local Markdown convention: child issues in issues/, Type/Label, Status, Assignee, and Blocked by metadata. Open means not yet resolved; claim before work. Resolve by appending Answer and a gist/link here. Frontier is open, unassigned children whose blockers are resolved, ordered numerically. The user has now requested a GitHub execution backlog: [Synthetic ingestion pipeline roadmap](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/2) and [ordered implementation issues](../../backend/ingestion/issues.md). GitHub tracks implementation status; these local tickets retain decision context. Creating implementation issues does not resolve the open design questions.
- Consult wayfinder, grilling, and domain-modeling for decision sessions; research for external facts. Charting may resolve research tickets only; human decisions remain open.
- Architecture reference: /home/nvidia/Documents/patient360-architecture copy.html and the provided screenshot. Repository baseline: backend/deploy/patient360/compose.yaml, sql/fhir/01-init.sql, stores/init/qdrant.sh, stores/openfga/model.fga, and stores/init/openfga.sh. The hybrid RAG overlay is a separate deployment using Elasticsearch; its Milvus service is disabled.
- Local branch: ingestion-pipeline, created from the current checkout while preserving pre-existing staged and unstaged work. The backend reorganization publishes the plan and local issues on this branch; unrelated working-tree changes remain local.
- Proposed sequence and current-state evidence: [Ingestion planning guide](../../backend/ingestion/plan.md). That guide is a proposal; resolved decisions live only in their tickets.
- Starting preference pending user reply: batch first, 10-patient smoke fixture then 100-patient seed, linked notes from the same Synthea histories. The note-generator project/API URL has been requested and is not yet supplied.
- Vocabulary for discussion: source FHIR bundle, opaque patient key, generated note, sanitized note, chunk, grant, and published batch. De-identification with linkable patient keys must not be represented as a guarantee of irreversible anonymization. New glossary entries wait for agreed meanings.

## Decisions so far

- [Verify Synthea, Presidio, and embedding integration contracts](issues/02-source-and-model-contracts.md): published source/export, de-identification, vector, and filter contracts documented; serving-profile limits and live readiness still require verification.

## Not yet specified

- Generator-specific integration choices beyond the public contract, depending on the project the user supplies and the failure modes its examples reveal.
- Further clinical coverage and evaluation cases exposed by inspecting the first linked synthetic records and notes.
- Capacity tuning and additional recovery cases exposed by the chosen cohort, model contract, and first implementation measurements.

## Out of scope

- Running the ingestion pipeline, populating stores, or deploying new services during this planning effort.
- Real patient data and claims of regulatory compliance or guaranteed anonymization.
- DICOM header stripping/defacing, VLM enrichment, imaging segmentation, and document/OCR ingestion.
- Interactive /ingest upload API and human review UI implementation for the first batch milestone; raw or rejected artifacts still need a handling policy.
- Reranker model selection, deployment, and ranking optimization. This map specifies the authorization and candidate handoff needed later.
- Replacing the separate Elasticsearch RAG overlay, modifying the clinical agent/UI, or broad production infrastructure hardening.
