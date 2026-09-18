# Choose note de-identification and chunk boundaries

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: none
Blocked by: 02, 04, 06

## Question

What Presidio policy and chunking contract will preserve clinical utility while preventing identifiers from reaching embedding requests, vector payloads, or logs?

Define recognizers/languages, structured identifiers supplied as detection hints, replacement and date handling, treatment of missed/ambiguous entities, sanitized error reporting, and review/quarantine behavior. Presidio detection must be validated against planted synthetic identifiers; it is not proof of complete anonymization.

Proposed order: validate linked note -> de-identify -> validate sanitized text -> tokenize/chunk -> embed. Specify section boundaries, token budget/overlap within the verified model limit, tokenizer/model/version provenance, sanitized offsets, and deterministic chunk IDs. Decide whether known synthetic adversarial notes are admitted only to an isolated evaluation corpus; text remains untrusted data throughout.

## Comments

### Resolved identity and date policy — 2026-09-17

Apply the amended [Define patient identity, linkage, and source provenance](04-identity-and-provenance.md#answer): preserve synthetic event dates, retain birth year only in prepared structured data, and do not enrich notes, embedding requests, or vector metadata with full DOB. The current source template does not include a birth-date field; explicitly handle any future source note that does before accepting it under this policy. Reconcile narrative age treatment with the imported FHIR plan's 90+ rule here. Preserve clinical detail while removing personal/contact identifiers. The temporary approval for internal raw non-patient `source_id` columns does not permit those IDs in note text, embeddings, or application output. Specify recognizers and failure handling here; raw FHIR must not pass through unchecked.

### Approved evaluation input — 2026-09-18

[Define clinically linked synthetic-note generation](06-note-generation-contract.md#answer) is resolved. Eight attack variants and three unchanged controls are now reproducible restricted raw artifacts; see [fixture validation](../../../backend/ingestion/evaluation-validation.md). They must undergo the same identifier sanitization policy as clinical notes, while preserving attack passages in isolated evaluation text to test downstream resistance. Do not mistake a created fixture corpus for completed model-security evaluation.

## Answer

Locked 2026-09-18. Implemented in `backend/app/patient360/deid.py` and `backend/ingestion/notes.py`. Presidio is an optional extra (`presidio-analyzer==2.2.358`, `presidio-anonymizer==2.2.358`); the same regex/hint policy runs in CI without spaCy models. `deid_version` is `p360-deid-1.0`.

- Language: English only.
- Recognizers: `PERSON`, `DATE_TIME`, `AGE`, `LOCATION`, `PHONE`, `EMAIL`, `ID`, plus a custom race/ethnicity word list. Worker-only hints (display names, exact DOB, MRN, phones) feed an ad-hoc recognizer and never enter embeddings, Qdrant payloads, citations, or ordinary logs.
- Replacements: `<PERSON>`, `<DOB>`, `<PHONE>`, `<EMAIL>`, `<ID>`, `<LOCATION>`, `<ETH>`. Age ≥ 90 becomes `90+`; younger ages stay. Synthetic clinical event dates stay. Exact DOB matching a hint, or the Synthea opening “Patient is a N year-old … born …” clause, is always redacted. Ambiguous `DATE_TIME` that is not a known DOB is kept.
- Order: validate linked note → de-identify whole note → canary → chunk → embed. Canary scans for registry names, exact DOB strings, MRN, and raw `source_id`. Any hit → MinIO `quarantine/` + unpublished row + `ingest` audit outcome 8; never embed, never publish.
- `[EVALUATION ATTACK PASSAGE]` text is preserved after identifier sanitization. Eval corpus uses collection `note_chunks_eval`.
- Chunk budget until live tokenizer verify: 384 tokens / 48 overlap (whitespace approximation). Deterministic point id = UUID5(`3c0a1f5e-8b2d-4e91-9c47-2a6f0d8e1b33`, `{note_id}:{chunk_index}:{deid_version}`). Offsets against sanitized text.
