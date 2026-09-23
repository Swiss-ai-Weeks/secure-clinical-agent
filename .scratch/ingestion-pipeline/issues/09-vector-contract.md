# Choose the embedding and Qdrant note-chunk contract

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Codex
Blocked by: 02, 07, 08

## Question

What exact model/request and Qdrant collection/payload schema will make note ingestion reproducible and safely retrievable?

Confirm the running model ID, passage/query modes, vector dimension, tokenizer limits, normalization/distance, batch limits, and model/image version. The initializer currently specifies note_chunks with 2048 dimensions and Cosine; verify compatibility rather than inferring it from the image name. Decide payload fields/indexes for sanitized text, patient/document/chunk IDs, source provenance, classification, processing/model versions, and publication state.

Choose deterministic upsert IDs, replacement/deletion semantics, compatibility checks for an existing collection, and reindex strategy for a model/dimension change. A future retrieval adapter must embed queries compatibly, authorize/filter candidates before exposing text, and pass only allowed candidates to a later reranker. Reranker model selection/deployment is outside this ingestion map.

## Earlier answer (superseded by the final answer below)

Locked 2026-09-18. Collection `note_chunks` (and isolated `note_chunks_eval`) is 2048-d Cosine. Live embed NIM (`nvidia/llama-nemotron-embed-vl-1b-v2`, `127.0.0.1:8001`) uses `input_type=passage` for chunks and `input_type=query` for search, `truncate=NONE`. Verify model id and dimension before the first write; an existing collection with the wrong size fails closed and is never dropped.

Payload: `{patient_key, note_id, confidentiality, sensitivity, dept, published, provenance, chunk_index, deid_version, text}`. Keyword indexes on `patient_key`, `confidentiality`, `published`. Deterministic UUID5 point ids. Replays upsert the same ids. Model/dimension change requires a new collection name, not an in-place drop. Offline tests use a keyword `NotesIndex` with the same payload contract.

### User-confirmed collection/versioning amendment — 2026-09-18

The user accepted retaining the earlier approved strategy in the acceptance discussion (“q1 yes lets do that”). This amendment takes precedence over the fixed initial collection names above: use separate clinical and evaluation physical collections tied to the validated embedding contract. Query embeddings and the selected collection must share that contract; matching vector dimensions alone is insufficient. Preserve existing collections and validate replacements before switching the backend's active reference.

Retain the previously accepted staged document-version replacement: prepare and validate the complete replacement before admitting it to reads, then retire the earlier version. Stricter security labels immediately withhold the earlier version. Collection switching alone does not coordinate publication, SQL state and grants.

Exact contract identity, payload/index/point-ID details and tokenizer/batch admission evidence still need reconciliation with this strategy before implementation acceptance. In particular, the preceding compact payload and note/index-only IDs are not evidence that versioned replacement is implemented. A resolved policy ticket does not establish a verified vector pipeline. [Acceptance evidence and handoff](11-acceptance-and-handoff.md) tracks the current discussion.

### Reopened for remaining contract details — 2026-09-18

The acceptance discussion reconfirmed the strategy but exposed unresolved technical details already owned by this question. Reopened rather than duplicating them in a new ticket: exact tokenizer/serving admission and overhead, bounded operational batch behavior, embedding-contract identity, complete versioned metadata/index schema and point-ID inputs. Existing accepted passage/query conventions, 2,048-dimensional Cosine target, collection/versioning and no-drop decisions remain in force. Resume with harmless model/tokenizer measurements before finalizing the schema; do not re-ask the user to approve settled choices. The [acceptance decision](11-acceptance-and-handoff.md#answer) specifies how implementation will be judged.

### Measured tokenizer admission and batch behavior — 2026-09-18

Claimed and completed harmless live checks with the downloaded tokenizer and `tokenizers==0.22.2`. [Readiness evidence](../../../backend/ingestion/embedding-readiness.md#tokenizer-boundary-and-bounded-batch-verification--2026-09-18) and the [reproducible probe](../../../backend/ingestion/probes/embedding_contract.py) own the measurements: local mode-prefixed/special-token counts matched the tested server inputs, both modes accepted 4,096 formatted tokens and rejected 4,097, and passage batches of 1/8/16/32 passed. Full formatted counting is required because prefix overhead varies with token boundaries. Preserve the approved 512-token content budget and up-to-64 overlap, with independent 4,096-token serving admission. Start with an operational client batch of eight, without claiming a measured server maximum.

The runtime still uses the inspected image digest, but concurrent deployment changes restored a mutable image reference and the failing shell-based Docker health probe; the HTTP service works. These changes are recorded in readiness evidence, not silently overwritten by this measurement session.

### Heading-context answer — approved 2026-09-18

The user answered “yes”: every split chunk carries its section's sanitized source heading, counted within the submitted text's 512-token budget. Keep that context separate from the body’s exact citation offsets. Repeated context must not be presented as an adjacent source span, and no patient details may be inferred or added. No production chunker was changed by this decision.

## Answer

Resolved 2026-09-18 after the user reconfirmed the collection/chunking/versioning strategy, accepted the heading choice, and the harmless tokenizer/boundary/batch probes passed. The technical encodings below implement those choices; they are an implementation contract, not a claim that ingestion, publication or retrieval passed. This answer supersedes the earlier compact payload and fixed-collection answer.

### Model and input admission

- Use `nvidia/llama-nemotron-embed-vl-1b-v2`, the inspected image digest and model/tokenizer file hashes in [embedding readiness](../../../backend/ingestion/embedding-readiness.md). Pin the actual image digest; `latest` is not an immutable identity. Preserve these asset hashes in a restricted deployment manifest and verify the mounted files before admission after startup/replacement.
- Send sanitized text as `input`, explicit `input_type: passage` for chunks or `query` for queries, `encoding_format: float`, `truncate: NONE`. Use the verified native 2,048-dimensional output and Cosine distance. Do not add the server's mode prefix or generation chat template to HTTP text, and do not apply a second client normalization step.
- Count content with the pinned local tokenizer (`tokenizers==0.22.2`, no padding or truncation, `add_special_tokens=False`). Count admission separately by encoding the exact `passage: ` or `query: ` prefix plus input with its special-token postprocessor enabled. Require the complete count to be at most 4,096; retain server-side rejection and treat a local/server disagreement as a contract failure. The tested character limit is a separate constraint; keep text below it too.
- Start with eight chunks per sequential HTTP request. Every input must pass individual admission before sending. This is a tested operational choice, not the server maximum. Reject malformed output, missing/duplicate/out-of-range response indices, wrong model identity/dimensions, zero or non-finite vectors. Associate results by their response indices, never assume array order.
- Cache only validated vectors, scoped to deployment and corpus, keyed by exact input bytes, input mode and embedding-contract identity. Reuse that cache on retries; validate current access metadata separately. Cache files and responses are not an authorization source. GPU results need not be bitwise identical across fresh runs.

### Chunk text and citations

- Apply the [approved section-aware chunking policy](07-deid-and-chunking.md#user-confirmed-chunking-amendment--2026-09-18). `text` is the exact contiguous body substring in the versioned sanitized note. `start_offset` and `end_offset` are half-open Unicode code-point indices, so `sanitized_note[start_offset:end_offset] == text`; do not collapse whitespace or normalize Unicode after calculating them.
- Store `heading_context` separately, copied from the nearest enclosing sanitized section heading, with `heading_start_offset` and `heading_end_offset` pointing to that source heading. Use an empty string and null heading offsets for unheaded text. Do not duplicate a heading already contained in the body slice. The exact embedding input is `heading_context + "\n\n" + text` when nonempty, otherwise `text`.
- The full submitted input, including that repeated heading, must contain at most 512 content tokens. Up to 64 body tokens overlap when splitting a long section; headings are not overlap. Prefer paragraph/sentence boundaries with deterministic tokenizer-aware fallback, and cover source body text without silent omission. If heading context leaves no usable body budget, fail preparation with a safe reason rather than dropping/truncating it.
- The full note artifact preserves headings and whitespace. Body citations identify the document revision and exact body offsets; any displayed heading cites its own source offsets. No citation may point to raw text or treat prefixed context as a contiguous body span.

### Identities and versioning

Use canonical JSON encoded as UTF-8 (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, no non-finite numbers) and SHA-256 for version hashes. Sort/deduplicate set-valued policy lists before hashing; do not normalize or rewrite source text. Hashes are lowercase hexadecimal. These are deterministic implementation conventions, not new source identities.

- `embedding_contract_id`: hash a versioned manifest containing image digest, served model ID, runtime release/API/backend, downloaded model/config/tokenizer/processor file hashes, local tokenizer-library version, measured mode formatting and special-token rules, input limits, output encoding/dimensions, distance and client normalization policy. Record automatic serving-profile selection honestly (`N/A` from metadata), with GPU architecture and explicit serving overrides; do not invent a profile identifier. A changed serving setup requires revalidation before use with the active contract.
- `chunk_policy_id`: hash the chunker policy version, tokenizer identity, 512/64 budgets, heading/input construction, boundary fallback and code-point offset convention.
- `note_id`: reuse the registry's stable opaque document identity and its mapping to the clinical note row. Do not copy a raw source document identifier or an arbitrary narrative identifier. `source_note_id` is the opaque original-note identity for an evaluation variant/control, or the same `note_id` for an ordinary clinical note. Restricted source links remain in provenance storage.
- `document_version`: hash exact sanitized note bytes plus sanitization policy, trusted patient/source-note linkage and all inherited security/provenance metadata including label-policy version. Changed text, labels or sanitization policy must produce a distinguishable revision. Grant membership changes do not reidentify the document; current grants are checked at reads.
- `publication_id`: hash deployment/corpus, `note_id`, `document_version`, `chunk_policy_id` and `embedding_contract_id`. This identifies the complete prepared rendition whose eligibility is tracked by the trusted backend.
- `chunk_id` and Qdrant point ID: the same UUID5, using namespace `3c0a1f5e-8b2d-4e91-9c47-2a6f0d8e1b33` and a canonical JSON name containing `publication_id`, zero-based chunk index, body/heading offsets and exact embedding-input SHA-256. Identical preparation reuses IDs; changed versions/settings cannot overwrite an older rendition accidentally.
- `batch_id` identifies source/load provenance, not visibility or point identity. A new retry/run receipt alone must not create new point IDs. Smoke and seed share the stable clinical corpus because smoke is a subset; evaluation has a separate corpus identity. Preserve subsequent batch associations in the trusted ingestion ledger rather than duplicating points for every run.

### Qdrant representation and compatibility

Physical collections are `note_chunks_clinical_<embedding_contract_id>` and `note_chunks_eval_<embedding_contract_id>` in the isolated deployment. Use unnamed 2,048-dimensional Cosine vectors. Preserve existing collections; validate the full contract registry, vector layout, distance and payload indexes before admission. Create missing collections/indexes deliberately; never interpret an authentication/network error as “collection missing”, and never drop a collection to repair incompatibility.

Required payload fields:

| Fields | Type and meaning |
| --- | --- |
| `payload_schema_version` | Integer `1` for this payload contract |
| `deployment_id`, `corpus_id`, `corpus_kind` | Nonempty scope strings; kind is `clinical` or `evaluation` |
| `patient_key`, `note_id`, `source_note_id`, `cite_id`, `chunk_id` | Opaque trusted identities and application citation identity; `chunk_id` equals point UUID |
| `document_version`, `publication_id`, `batch_id` | Nonempty revision, eligible-rendition and originating-batch identities |
| `embedding_contract_id`, `chunk_policy_id`, `deid_version`, `label_version` | Nonempty processing and label-policy identities |
| `confidentiality`, `sensitivity`, `internal`, `provenance`, `dept` | Validated access metadata: approved classification string, explicit string list (including empty), boolean, approved provenance string, and explicit department string or null. Never infer grants from these fields or default missing restrictions to permissive values |
| `published` | Boolean; false while staged; necessary but insufficient for readability |
| `text`, `heading_context` | Exact sanitized body and separate sanitized heading; no raw identifiers |
| `start_offset`, `end_offset`, `heading_start_offset`, `heading_end_offset`, `chunk_index` | Body/index integers; heading offsets both integers or both null as described above |
| `content_token_count`, `input_token_count`, `embedding_input_sha256` | Exact unformatted/formatted counts and input hash validated before write |

Create keyword indexes on `deployment_id`, `corpus_id`, `corpus_kind`, `patient_key`, `note_id`, `document_version`, `publication_id`, `batch_id`, `embedding_contract_id`, `confidentiality`, `sensitivity`, `provenance` and `dept`; bool indexes on `internal` and `published`. Explicitly correct the earlier proposed keyword index for boolean `published`. No full-text or offset index is required for the initial retrieval contract. Opaque `p_...` keys are keywords, not UUID-typed values. [Qdrant's index reference](https://qdrant.tech/documentation/manage-data/indexing/) documents these types; check the deployed collection schema during implementation.

### Publication, replacement and reads

Only validated sanitized documents enter embedding. Store staged points with trusted complete metadata and an immutable prepared-rendition manifest listing the expected point IDs. Before eligibility, the backend verifies the sanitized artifact/SQL linkage, actual complete vector set and grants. A list of intended points or a fabricated artifact reference is not this evidence.

Bind each query to an explicit `(embedding_contract_id, physical_collection)` pair and the current authorized patient scope plus eligible `publication_id` set before retrieving any text. Use trusted metadata to narrow scope, then validate returned security metadata and recheck access at content handoff. Caller filters only narrow this set. Missing eligibility, contract or authorization dependencies fail closed. Alias switching alone cannot make this change atomic across query model, SQL and grants.

Stage full replacements, then atomically change trusted eligible-rendition state and retire the old rendition from reads. If restrictions tighten, withhold the old rendition immediately. Retries cannot republish a retired version or revive grants; identical eligible renditions are checked and reused. Old physical points may remain for controlled later cleanup but must be excluded from reads, including shorter-document replacements. Source removals continue to require a separate explicit deletion workflow. Apply the [partial-batch policy](10-batch-lifecycle.md#user-approved-partial-batch-policy--2026-09-18) without bypassing policy-wide validation failures.

### Handoff and remaining implementation evidence

Implement the tokenizer/heading-aware chunker and response-validating embedding adapter, then the versioned payload/index/eligibility machinery and actual authorized search path. Reconcile the recorded deployment drift before runtime acceptance. Follow the [accepted pilot-to-seed checks](11-acceptance-and-handoff.md#answer). The live probe establishes model input/output behavior only; this resolution performs no collection writes, publishes no notes and does not certify the current sanitizer or retrieval implementation. Schema migrations and the trusted eligibility ledger remain implementation work under the lifecycle contract.

### Implementation checkpoint — 2026-09-18

The section-aware tokenizer chunker and validating passage adapter are implemented in the note worker. [Validation evidence](../../../backend/ingestion/vector-preparation-validation.md) records 68 passing tests, including harmless live inference, with six PostgreSQL tests skipped. Output consists of restricted unpublished preparation/embedding artifacts; the former local-dictionary publication shortcut is disabled. Full contract/document/publication identities, versioned Qdrant schema/writes and trusted eligibility remain the next implementation stage. The accepted contract above is unchanged.
