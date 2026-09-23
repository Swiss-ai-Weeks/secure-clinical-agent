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

**Evaluation variant**: A separately identified test copy of a source clinical note whose original narrative is preserved and an attack passage is added. It belongs to the adversarial evaluation corpus, never the clinical seed.

**Unchanged control**: The original note used to compare a legitimate clinical task against its evaluation variants. It checks that useful, supported answers remain possible when no attack passage is present.

## Ingestion identity language

**Opaque patient key**: The application's patient identity that does not expose the source patient identifier. The same source patient retains this key across smoke/seed batches, retries, and reprocessing within its source namespace.

**Source namespace**: The boundary within which source identities refer to the same patients and records. Unrelated datasets do not become the same identity space merely because an identifier or demographic value matches.

**Restricted provenance**: The source links needed by an authorized operator to trace prepared records back to their origin. These links are separate from the safe opaque citations exposed by the application.

**Pseudonymized synthetic data**: Generated clinical records whose source identities are replaced with opaque identities while restricted links preserve traceability. Retained linkage and clinical detail mean this term does not assert irreversible anonymity.

## Ingestion publication language

**Quarantined note**: A whole note withheld from embedding and retrieval because sanitization or its validation failed. It requires corrected processing and successful validation before admission.

**Partial ingestion batch**: A batch in which some notes have become eligible for authorized retrieval while other notes remain withheld. It is not a claim that the complete clinical seed passed acceptance.

## Ingestion retrieval language

**Heading context**: A sanitized source heading carried with a passage to preserve its section meaning. It is distinct from the passage body and retains its own source location.

**Embedding contract**: The versioned agreement that makes stored passage vectors and query vectors compatible. A replacement contract is validated before it becomes eligible for retrieval.

**Document version**: A complete prepared revision of a note, distinct from the note's stable identity. Changed content or inherited restrictions can create a new revision while preserving the original note identity.
