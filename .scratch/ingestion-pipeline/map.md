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
- Local branch: ingestion-pipeline, created from the current checkout while preserving pre-existing staged and unstaged work. The user subsequently requested publication of all pending repository changes, including the product documents, learning assets, and document moves. The user subsequently requested the synthetic `.data` snapshot be pushed on 2026-09-18; selected artifacts and registry snapshots are now included. Credential-bearing PostgreSQL rebuild backups and transient/debug files remain ignored. See [.data sharing scope](../../.data/README.md).
- Proposed sequence and current-state evidence: [Ingestion planning guide](../../backend/ingestion/plan.md). That guide is a proposal; resolved decisions live only in their tickets.
- Main schema integration: [checkpoint](../../backend/ingestion/schema-integration.md) records the user's reconciliation choices, the backed-up PostgreSQL volume replacement, runtime validation, and remaining adapter work. Database initialization does not load or publish the clinical seed.
- Vocabulary for discussion: source FHIR bundle, opaque patient key, generated note, sanitized note, chunk, grant, and published batch. De-identification with linkable patient keys must not be represented as a guarantee of irreversible anonymization. New glossary entries wait for agreed meanings.

## Decisions so far

- [Identify the synthetic-note generator and obtain its API contract](issues/01-note-generator-input.md): Synthea's pinned FHIR export supplies linked raw encounter notes; inspected contract and repeatable source-worker evidence recorded in the ticket.
- [Verify Synthea, Presidio, and embedding integration contracts](issues/02-source-and-model-contracts.md): published source/export, de-identification, vector, and filter contracts documented; serving-profile limits and live readiness still require verification.
- [Choose the first cohort and ingestion success criteria](issues/03-cohort-and-success.md#answer): approved the reproducible development cohort, structured resource scope, three source-grounded demonstrations with access checks, and a separate adversarial evaluation corpus.
- [Define patient identity, linkage, and source provenance](issues/04-identity-and-provenance.md#answer): stable opaque patient identities, birth year only, temporary internal raw source resource IDs with a restricted-provenance follow-up, and an authorized demo database rebuild.

- [Choose the FHIR-to-PostgreSQL projection and update rules](issues/05-fhir-projection.md#answer): approved strict code-aware projection, stable opaque identities and upserts, rejected removals, and reviewed fixture sensitivity labels; [structured validation](../../backend/ingestion/structured-validation.md) records the committed smoke/seed loads and replay checks.

- [Define clinically linked synthetic-note generation](issues/06-note-generation-contract.md#answer): approved eight isolated attack variants with unchanged controls and full-path resistance criteria; a reproducible local corpus is implemented, while sanitization and security evaluation remain downstream.

- [Choose note de-identification and chunk boundaries](issues/07-deid-and-chunking.md#user-confirmed-chunking-amendment--2026-09-18): user reconfirmed section-aware 512/64 model-token chunking and exact sanitized citations; the worker now uses the pinned tokenizer with exact separate heading/body offsets; the separate application upload helper remains outside this change.

- [Choose the embedding and Qdrant note-chunk contract](issues/09-vector-contract.md#answer): finalized measured token admission, sanitized heading context, contract-specific collections, versioned UUID points and typed payload/index requirements; unpublished worker chunk/embedding artifacts are implemented and tested; versioned stores, trusted eligibility and live seed acceptance remain pending.

- [Choose batch orchestration, publication, and recovery](issues/10-batch-lifecycle.md#user-approved-partial-batch-policy--2026-09-18): validated notes may become eligible independently of quarantined notes; partial runs remain explicitly partial and require real publication/access enforcement.

- [Define acceptance evidence and the implementation handoff](issues/11-acceptance-and-handoff.md#answer): approved the three-example pilot, top-five evidence gate, smoke-to-seed progression, failure/replay checks and explicit partial-run acceptance rules; implementation and live acceptance remain pending.

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
