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

The current resource JSONB columns are unconstrained: choose an explicit safe projection or omission policy, including nested extensions and narrative; never equate flattening with de-identification. Conditions/observations currently use random default UUIDs without source uniqueness. Define deterministic source keys/upserts, update/delete handling, and migrations that also work with existing PostgreSQL volumes (init SQL alone is insufficient). Link acceptance examples to the resolved cohort.

## Comments

### Resolved identity and date policy — 2026-09-17

Apply [Define patient identity, linkage, and source provenance](04-identity-and-provenance.md#answer). In particular, full generated birth dates are approved for authorized structured patient records; the existing `birth_year` column alone cannot represent that decision. Specify a date-column migration for existing volumes, explicit projection, and date/age validation. Use the registry's stable opaque resource IDs for replay and preserve clinical event dates/times. The approved structured DOB must not be copied into note text or embedding/vector payloads. Field allowlists, coding/component representation, and source update/delete behavior remain this ticket's decisions.
