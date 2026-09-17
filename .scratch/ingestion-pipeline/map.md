# Plan the Patient360 synthetic ingestion pipeline

Label: wayfinder:map
Status: active

## Destination

A reproducible batch worker for seeding Patient360 with linked synthetic patients and notes: Synthea FHIR projected into PostgreSQL, and de-identified, embedded, ACL-tagged note chunks published to Qdrant. The user authorized incremental execution on 2026-09-17. Completion still requires resolved data, identity, authorization, lifecycle, and acceptance contracts plus runtime evidence.

## Notes

- Execution override (2026-09-17): the user now requests implementation using Synthea and the existing plan. Implement and test the reproducible batch worker incrementally, including local synthetic fixtures as needed. Keep unresolved product/security decisions explicit; do not equate worker tests with production readiness. This supersedes the earlier planning-only restriction.
- Session handoff: [Resume ingestion: source data to authorized vector search](../../backend/ingestion/NEXT-STEPS.md) records completed source generation, local artifacts, and the remaining path through sanitization, stores, publication, and authenticated search. Source publication does not publish the raw seed into stores.
- Canonical tracker is the existing local Markdown convention: child issues in issues/, Type/Label, Status, Assignee, and Blocked by metadata. Open means not yet resolved; claim before work. Resolve by appending Answer and a gist/link here. Frontier is open, unassigned children whose blockers are resolved, ordered numerically. The user has now requested a GitHub execution backlog: [Synthetic ingestion pipeline roadmap](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/2) and [ordered implementation issues](../../backend/ingestion/issues.md). GitHub tracks implementation status; these local tickets retain decision context. Creating implementation issues does not resolve the open design questions.
- Consult wayfinder, grilling, and domain-modeling for decision sessions; research for external facts. Charting may resolve research tickets only; human decisions remain open.
- Architecture reference: /home/nvidia/Documents/patient360-architecture copy.html and the provided screenshot. Repository baseline: backend/deploy/patient360/compose.yaml, sql/fhir/01-init.sql, stores/init/qdrant.sh, stores/openfga/model.fga, and stores/init/openfga.sh. The hybrid RAG overlay is a separate deployment using Elasticsearch; its Milvus service is disabled.
- Local branch: ingestion-pipeline, created from the current checkout while preserving pre-existing staged and unstaged work. The user subsequently requested publication of all pending repository changes, including the product documents, learning assets, and document moves. Ignored datasets and restricted local evidence remain local.
- Proposed sequence and current-state evidence: [Ingestion planning guide](../../backend/ingestion/plan.md). That guide is a proposal; resolved decisions live only in their tickets.
- Main schema integration: [checkpoint](../../backend/ingestion/schema-integration.md) records the imported FHIR plan/schema and the outstanding differences owned by the projection, note, and lifecycle tickets. A clean Git merge does not resolve those contracts or apply the SQL to existing stores.
- Vocabulary for discussion: source FHIR bundle, opaque patient key, generated note, sanitized note, chunk, grant, and published batch. De-identification with linkable patient keys must not be represented as a guarantee of irreversible anonymization. New glossary entries wait for agreed meanings.

## Decisions so far

- [Identify the synthetic-note generator and obtain its API contract](issues/01-note-generator-input.md): Synthea's pinned FHIR export supplies linked raw encounter notes; inspected contract and repeatable source-worker evidence recorded in the ticket.
- [Verify Synthea, Presidio, and embedding integration contracts](issues/02-source-and-model-contracts.md): published source/export, de-identification, vector, and filter contracts documented; serving-profile limits and live readiness still require verification.
- [Choose the first cohort and ingestion success criteria](issues/03-cohort-and-success.md#answer): approved the reproducible development cohort, structured resource scope, three source-grounded demonstrations with access checks, and a separate adversarial evaluation corpus.
- [Define patient identity, linkage, and source provenance](issues/04-identity-and-provenance.md#answer): stable opaque identities with restricted retraceability; preserve synthetic clinical dates and structured birth dates without adding DOB to notes or embeddings.

## Not yet specified

- Additional source/export edge cases beyond the validated Synthea cohort and the handling they may require in downstream adapters.
- Further clinical coverage and evaluation cases exposed by inspecting the first linked synthetic records and notes.
- Capacity tuning and additional recovery cases exposed by the chosen cohort, model contract, and first implementation measurements.

## Out of scope

- Production rollout and publication of a seed before its cross-store and authorization acceptance checks pass. Local implementation and synthetic validation are now in scope.
- Real patient data and claims of regulatory compliance or guaranteed anonymization.
- DICOM header stripping/defacing, VLM enrichment, imaging segmentation, and document/OCR ingestion.
- Interactive /ingest upload API and human review UI implementation for the first batch milestone; raw or rejected artifacts still need a handling policy.
- Reranker model selection, deployment, and ranking optimization. This map specifies the authorization and candidate handoff needed later.
- Replacing the separate Elasticsearch RAG overlay, modifying the clinical agent/UI, or broad production infrastructure hardening.
