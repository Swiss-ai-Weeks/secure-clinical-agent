# Synthetic ingestion pipeline

This directory is the home for Patient360 ingestion work. The first worker stage now generates reproducible Synthea FHIR source batches and extracts linked raw clinical notes. Downstream de-identification, PostgreSQL loading, embedding, Qdrant writes, grants, and publication remain to be implemented.

- [Start here next session: vector storage and search handoff](NEXT-STEPS.md)
- [Worker commands and steps to complete the pipeline](RUNBOOK.md)
- [Source worker](worker.py) and [pinned configuration](config/synthea.json)
- [Inspected Synthea generator contract](research/synthea-generator-contract.md)

- [Ordered GitHub implementation backlog](issues.md)
- [Ingestion roadmap](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/2)
- [Proposed sequence and data-flow diagram](plan.md)
- [Wayfinder map and local decision issues](../../.scratch/ingestion-pipeline/map.md)
- [Synthea, Presidio, Nemotron, and Qdrant research](research/source-model-contracts.md)
- [Patient360 deployment and store initialization](../deploy/patient360/)

The planned paths are Synthea FHIR → de-identified structured projection → PostgreSQL, and linked synthetic clinical notes → Presidio → chunks and ACL metadata → Nemotron embeddings → Qdrant. Patient keys and source provenance must agree across both paths. Authorization is checked at retrieval time; reranking is a later stage.

Put future generators/adapters, FHIR transforms, de-identification, chunking, embedding clients, grant integration, batch orchestration, and their tests here. Add package/layout details when the open decisions settle. Keep synthetic fixtures small; generated datasets, raw notes, credentials, and model caches belong in ignored local storage rather than source control.

The user selected Synthea and approved 10 smoke patients / 100 seed patients. Remaining cohort and security decisions stay explicit in the map. Generated source artifacts live under ignored `.data/ingestion/`; they are unsanitized and unpublished.
