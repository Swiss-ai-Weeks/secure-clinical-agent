# Choose note de-identification and chunk boundaries

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
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
