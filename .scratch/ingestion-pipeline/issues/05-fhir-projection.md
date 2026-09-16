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
