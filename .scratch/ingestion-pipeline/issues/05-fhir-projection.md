# Choose the FHIR-to-PostgreSQL projection and update rules

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: 04

## Question

How should Synthea FHIR R4 populate the existing patients, conditions, and observations tables while preserving useful clinical meaning and removing identifiers?

Specify reference resolution, coding/system selection, numeric/text/component observations, units, clinical/status fields, dates, unsupported resources, and invalid/missing references. Decide whether additional resources require later schema migrations.

Main's schema now has top-level resource JSONB allowlists, source uniqueness, component observations, and patient-scoped foreign keys. Specify the nested safe projection and omissions rather than passing raw objects through those allowlists; flattening alone is not de-identification. Use its temporarily approved raw non-patient `source_id` upsert keys within the agreed source namespace and define update/delete handling. The user approved a backed-up volume replacement for this demo bootstrap; worker retries must not reset the database. Link acceptance examples to the resolved cohort.

## Comments

### Resolved identity and date policy — 2026-09-17

Apply the amended [Define patient identity, linkage, and source provenance](04-identity-and-provenance.md#answer): birth year only, opaque patient keys, temporary raw non-patient source resource IDs, and preserved clinical event dates/times. No full-DOB column migration is required. Keep full DOB out of prepared records, note enrichment, and embedding/vector payloads. Field allowlists, coding/component representation, and source update/delete behavior remain this ticket's decisions.

### Main schema imported — 2026-09-17

[Main schema integration checkpoint](../../../backend/ingestion/schema-integration.md) records the imported schema, the user's reconciliation choices, and runtime validation. Birth-date precision, temporary source-ID storage, and volume replacement are now decided. Key representation, nested projection, labels, and update/delete semantics still need adapter work. [Move source resource identifiers into restricted provenance](12-restrict-source-resource-identifiers.md) tracks the explicitly deferred source-ID restriction.
