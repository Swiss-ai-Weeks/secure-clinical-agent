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

Main's schema now has top-level resource JSONB allowlists, source uniqueness, component observations, and patient-scoped foreign keys. Specify the nested safe projection and omissions rather than passing raw objects through those allowlists; flattening alone is not de-identification. Reconcile its raw `source_id` upsert keys with the resolved opaque-identity contract, define update/delete handling, and provide migrations that also work with existing PostgreSQL volumes (init SQL alone is insufficient). Link acceptance examples to the resolved cohort.

## Comments

### Resolved identity and date policy — 2026-09-17

Apply [Define patient identity, linkage, and source provenance](04-identity-and-provenance.md#answer). In particular, full generated birth dates are approved for authorized structured patient records; the existing `birth_year` column alone cannot represent that decision. Specify a date-column migration for existing volumes, explicit projection, and date/age validation. Use the registry's stable opaque resource IDs for replay and preserve clinical event dates/times. The approved structured DOB must not be copied into note text or embedding/vector payloads. Field allowlists, coding/component representation, and source update/delete behavior remain this ticket's decisions.

### Main schema imported — 2026-09-17

[Main schema integration checkpoint](../../../backend/ingestion/schema-integration.md) compares the merged schema and shared resource plan with the approved ingestion decisions. Resolve the documented birth-date precision, raw source IDs/namespaces, migration/lifecycle, key representation, and scope differences before building the PostgreSQL adapter. The merge is textually clean; those design choices remain open. Existing source-worker tests pass, but the SQL has not been applied to the running stores.
