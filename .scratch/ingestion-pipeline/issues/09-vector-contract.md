# Choose the embedding and Qdrant note-chunk contract

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: none
Blocked by: 02, 07, 08

## Question

What exact model/request and Qdrant collection/payload schema will make note ingestion reproducible and safely retrievable?

Confirm the running model ID, passage/query modes, vector dimension, tokenizer limits, normalization/distance, batch limits, and model/image version. The initializer currently specifies note_chunks with 2048 dimensions and Cosine; verify compatibility rather than inferring it from the image name. Decide payload fields/indexes for sanitized text, patient/document/chunk IDs, source provenance, classification, processing/model versions, and publication state.

Choose deterministic upsert IDs, replacement/deletion semantics, compatibility checks for an existing collection, and reindex strategy for a model/dimension change. A future retrieval adapter must embed queries compatibly, authorize/filter candidates before exposing text, and pass only allowed candidates to a later reranker. Reranker model selection/deployment is outside this ingestion map.

## Answer

Locked 2026-09-18. Collection `note_chunks` (and isolated `note_chunks_eval`) is 2048-d Cosine. Live embed NIM (`nvidia/llama-nemotron-embed-vl-1b-v2`, `127.0.0.1:8001`) uses `input_type=passage` for chunks and `input_type=query` for search, `truncate=NONE`. Verify model id and dimension before the first write; an existing collection with the wrong size fails closed and is never dropped.

Payload: `{patient_key, note_id, confidentiality, sensitivity, dept, published, provenance, chunk_index, deid_version, text}`. Keyword indexes on `patient_key`, `confidentiality`, `published`. Deterministic UUID5 point ids. Replays upsert the same ids. Model/dimension change requires a new collection name, not an in-place drop. Offline tests use a keyword `NotesIndex` with the same payload contract.
