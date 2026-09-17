# Project language

Patient360 is the clinical-agent product in this repository. The RAG overlay is a document pipeline that prepares and searches documents locally, then uses a hosted model to generate grounded responses.

## RAG deployment language

## Language

**Hybrid RAG**: Document preparation, retrieval, and storage happen in our environment; answer generation uses NVIDIA's hosted model.

**Registry credential**: Authorization to access NVIDIA container and model artifacts. Success here does not establish hosted inference permission.

**Hosted inference credential**: Authorization to invoke the configured NVIDIA-hosted language model. It may be different from the registry credential.

**Core blueprint baseline**: The selected ingestion, retrieval, storage, orchestration, and answer-generation paths, with optional blueprint branches explicitly excluded.

**Verified pipeline**: A running system that ingests a known document, retrieves its content, and generates an answer with a citation to that document. Static configuration validity alone does not establish this state.

## Ingestion evaluation language

**Smoke fixture**: The small synthetic cohort used for a quick check before exercising the full clinical seed. This project's fixture contains 10 patients also present in the 100-patient seed; "smoke" describes the test's scope, not a clinical characteristic.

**Clinical seed**: The reproducible synthetic patient cohort and its linked clinical records and notes used for the development demonstration. Intentionally adversarial notes are excluded from this corpus.

**Adversarial evaluation corpus**: A separately labelled set of synthetic notes containing intentional prompt-injection attempts, used to evaluate handling of untrusted note content. It is distinct from the clinical seed.

## Ingestion identity language

**Opaque patient key**: The application's patient identity that does not expose the source patient identifier. The same source patient retains this key across smoke/seed batches, retries, and reprocessing within its source namespace.

**Source namespace**: The boundary within which source identities refer to the same patients and records. Unrelated datasets do not become the same identity space merely because an identifier or demographic value matches.

**Restricted provenance**: The source links needed by an authorized operator to trace prepared records back to their origin. These links are separate from the safe opaque citations exposed by the application.

**Pseudonymized synthetic data**: Generated clinical records whose source identities are replaced with opaque identities while restricted links preserve traceability. Retained linkage and clinical detail mean this term does not assert irreversible anonymity.
