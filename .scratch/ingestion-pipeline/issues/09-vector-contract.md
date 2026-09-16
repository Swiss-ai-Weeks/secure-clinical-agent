# Choose the embedding and Qdrant note-chunk contract

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: 02, 07, 08

## Question

What exact model/request and Qdrant collection/payload schema will make note ingestion reproducible and safely retrievable?

Confirm the running model ID, passage/query modes, vector dimension, tokenizer limits, normalization/distance, batch limits, and model/image version. The initializer currently specifies note_chunks with 2048 dimensions and Cosine; verify compatibility rather than inferring it from the image name. Decide payload fields/indexes for sanitized text, patient/document/chunk IDs, source provenance, classification, processing/model versions, and publication state.

Choose deterministic upsert IDs, replacement/deletion semantics, compatibility checks for an existing collection, and reindex strategy for a model/dimension change. A future retrieval adapter must embed queries compatibly, authorize/filter candidates before exposing text, and pass only allowed candidates to a later reranker. Reranker model selection/deployment is outside this ingestion map.
