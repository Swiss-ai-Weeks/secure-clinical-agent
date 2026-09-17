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

Apply [Define patient identity, linkage, and source provenance](04-identity-and-provenance.md#answer): preserve synthetic event dates and ages, with full synthetic birth dates retained only in authorized structured patient records. Do not enrich notes, embedding requests, or vector metadata with DOB. The current source template does not include a birth-date field; explicitly handle any future source note that does before accepting it under this policy. Preserve clinical detail while removing personal/contact identifiers, and keep raw linkage/provenance restricted. Specify recognizers and failure handling here; structured DOB retention does not imply that raw FHIR or arbitrary dates/identifiers may pass through unchecked.
