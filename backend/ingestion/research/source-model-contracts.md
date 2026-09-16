# Patient360 ingestion: source and model contracts

Research date: 2026-09-16. This answers the **Verify Synthea, Presidio, and embedding integration contracts** decision ticket. It establishes published facts and planning implications; no services were started or queried, and no generator API is assumed.

## Local configuration observed

The main checkout's [Patient360 Compose](../../deploy/patient360/compose.yaml) configures PostgreSQL 16, Qdrant **v1.13.6**, and `nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2:latest`, with embedding HTTP on host loopback port 8001. This is the Patient360 Qdrant stack, not the separate Elasticsearch overlay. Compose contains no Presidio or reranking service.

The [Qdrant initializer](../../deploy/patient360/stores/init/qdrant.sh) attempts to create `note_chunks` with **2048 dimensions, Cosine distance**, but creates no payload indexes and does not verify an existing collection's configuration. Therefore the script is configuration intent, not proof that the collection exists or has that schema.

The [FHIR initializer](../../deploy/patient360/sql/fhir/01-init.sql) has `patients`, `conditions`, `observations`, and `studies`. Its comment requires opaque `patient_key` and excludes names. `resource jsonb` remains a possible route for original identifiers; passing raw FHIR into it would not satisfy that intent. Conditions and observations default to random UUIDs, so the importer needs explicit source identity/idempotency handling.

## Synthea: generation and reference handling

Synthea supports FHIR R4, population size, population seed (`-s`), clinician seed (`-cs`), reference date (`-r YYYYMMDD`), local configuration and modules. A reproducible run manifest should pin the Synthea revision, Java/runtime, both seeds, reference date, geography, modules, population and exporter settings; a seed alone is not a sufficient reproducibility contract. This manifest recommendation is an inference from the available generation inputs. [Synthea README](https://github.com/synthetichealth/synthea)

FHIR export supports per-patient bundles and bulk NDJSON; transaction versus collection bundles is configurable. Set R4 and bundle settings explicitly and retain practitioner/hospital exports if the selected data references them. The initial flattener can support bundle input first; bulk input is a separate shape, not an interchangeable JSON file. [Synthea FHIR export documentation](https://github.com/synthetichealth/synthea/wiki/HL7-FHIR)

FHIR bundle `fullUrl` identifies the entry resource and can be a `urn:uuid:` identity. References require bundle-aware resolution, not simply splitting the final slash segment. Planning implication: index `fullUrl` plus resource type/id, resolve supported references before flattening, and quarantine unresolved or ambiguous patient links. Define handling of contained, relative, absolute and versioned references explicitly. The opaque patient mapping must join structured rows and note chunks consistently. [FHIR R4 bundle identity and reference rules](https://hl7.org/fhir/R4/bundle.html)

The user's forthcoming note-generator project/API remains unknown. Do not treat Synthea's CLI as that API or invent note-generation parameters.

## Presidio: detection is a component, not a completeness guarantee

Presidio separates sensitive-data detection from anonymization, supports predefined/custom recognizers, and explicitly does not guarantee discovery of all sensitive information. Planning implication: evaluate known synthetic identifiers, medical identifiers and clinical language, including false negatives and false positives; record recognizer/model/policy versions. Failed validation must not silently continue into embedding. [Presidio overview](https://presidio.dataprivacystack.org/)

Anonymizer operators act on detected spans and include replacement, redaction, masking and encryption. Generic entity replacement does not establish persistent patient identity. Current documentation also notes that hash behavior changed at version 2.2.361: random salt is the default, and consistent cross-call hashing needs explicitly managed salt. Pin the package version and design linkage separately instead of assuming any default anonymizer operator provides stable patient keys. [Presidio anonymizer](https://presidio.dataprivacystack.org/anonymizer/)

Recommended boundary for later decisions: validate identity → de-identify complete note → validate sanitized output → chunk → embed → attach trusted metadata → publish. Structured FHIR needs an explicit field allowlist/redaction policy as well; note sanitization does not sanitize `resource jsonb`. Presidio is not a prompt-injection sanitizer. Treat synthetic adversarial note text as untrusted content.

## Nemotron embedding: distinguish model card from serving profile

The configured model's published ID is `nvidia/llama-nemotron-embed-vl-1b-v2`. Use `input_type: passage` for indexed notes and `query` for retrieval queries; the model page warns that incorrect mode harms retrieval. [NVIDIA model page](https://build.nvidia.com/nvidia/llama-nemotron-embed-vl-1b-v2)

NVIDIA's **NIM 2.2** support matrix lists this VL model with **2048 output dimensions** and a default VL profile sequence limit of **2048 tokens**. Its text-only sibling has a different limit; do not copy the sibling's 8192-token specification. The current local `latest` image does not identify which NIM release/profile is actually running. [NIM 2.2 support matrix](https://docs.nvidia.com/nim/nemo-retriever/embedding/2.2/support-matrix.html)

The model card separately reports evaluation up to **10240 tokens** and maximum 2048-dimensional output. This describes model capability/evaluation, not evidence that this deployment accepts 10240-token requests. [NVIDIA-owned model card](https://huggingface.co/nvidia/llama-nemotron-embed-vl-1b-v2/blob/main/README.md)

The serving API documents `/v1/models`, `/v1/embeddings`, float output, dimensions and `truncate: START|END|NONE`. Recommended contract: explicit passage/query mode, float vectors of the verified collection size, tokenizer-aware chunk budgets and `truncate: NONE` to expose oversize input rather than silently dropping clinical content. Verify these fields against the deployed release. [NIM 2.2 API reference](https://docs.nvidia.com/nim/nemo-retriever/embedding/2.2/reference.html)

## Qdrant v1.13.6: metadata and filtering

The release-pinned API includes query filters, `must`/`should`/`must_not`, exact-value and any-of matching, payload indexes (including keyword, integer, bool, datetime and UUID), and filtered point queries. Keyword indexes fit opaque patient keys and categorical tags; UUID indexes require UUID-formatted values. Point identifiers accept unsigned integers or UUIDs, so arbitrary source-note strings should remain payload or map to deterministic UUIDs. [Qdrant v1.13.6 OpenAPI](https://raw.githubusercontent.com/qdrant/qdrant/v1.13.6/docs/redoc/master/openapi.json)

Payload arrays match when at least one element meets a condition. This supports tag sets, but does not itself express all-of authorization semantics. [Qdrant payload semantics](https://qdrant.tech/documentation/manage-data/payload/)

Planning implication: mandatory trusted filters should include the authorized patient/tenant scope, permitted sensitivity classes and publication state. Missing ACL metadata must fail ingestion. Tagging alone does not enforce authorization: the gateway must obtain current grants and build the filter before retrieval; revocations cannot depend solely on stale copied tags. No caller-supplied filter may widen that scope.

## Later reranking boundary

NVIDIA describes reranking as scoring the relevance of candidate passages to a query. Keep sanitized passage text, stable note/chunk identifiers and provenance available so a later reranker can reorder retrieved candidates. [NVIDIA reranking overview](https://docs.nvidia.com/nim/nemo-retriever/text-reranking/latest/overview.html)

Proposed boundary: current authorization → filtered vector retrieval → rerank only authorized sanitized candidates → retain identifiers/citations in results. Reranking must not fetch unrestricted neighboring chunks or expand the allowed set. Model choice, deployment and ranking evaluation remain future work.

## Runtime facts still unverified

Before implementation, record the embedding image digest, NIM release/profile, model ID, tokenizer limit and boundary behavior; test one query and passage for finite 2048-value output and correct batch indexing. Inspect Qdrant's actual collection size/distance/indexes and readiness. Check PostgreSQL's actual schema and initialized volumes. Measure Presidio against an explicit synthetic truth set. The research closes documentation uncertainty, not these runtime checks or the product decisions about identity, de-identification and authorization policy.
