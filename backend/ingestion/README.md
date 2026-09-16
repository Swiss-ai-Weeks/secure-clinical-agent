# Synthetic ingestion pipeline

This directory is the home for Patient360 ingestion work. It currently contains the implementation plan and source-contract research; no ingestion worker has been implemented yet.

- [Ordered GitHub implementation backlog](issues.md)
- [Ingestion roadmap](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/2)
- [Proposed sequence and data-flow diagram](plan.md)
- [Wayfinder map and local decision issues](../../.scratch/ingestion-pipeline/map.md)
- [Synthea, Presidio, Nemotron, and Qdrant research](research/source-model-contracts.md)
- [Patient360 deployment and store initialization](../deploy/patient360/)

The planned paths are Synthea FHIR → de-identified structured projection → PostgreSQL, and linked synthetic clinical notes → Presidio → chunks and ACL metadata → Nemotron embeddings → Qdrant. Patient keys and source provenance must agree across both paths. Authorization is checked at retrieval time; reranking is a later stage.

Put future generators/adapters, FHIR transforms, de-identification, chunking, embedding clients, grant integration, batch orchestration, and their tests here. Add package/layout details when the open decisions settle. Keep synthetic fixtures small; generated datasets, raw notes, credentials, and model caches belong in ignored local storage rather than source control.

Next inputs are the note-generator project/API and the initial cohort choice. See the map for dependencies and decisions already researched.
