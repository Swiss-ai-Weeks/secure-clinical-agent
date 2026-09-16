# Identify the synthetic-note generator and obtain its API contract

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: task
Label: wayfinder:task
Status: open
Assignee: none
Blocked by: none

## Question

Which project/API will generate the synthetic notes, and can its contract and a synthetic example be inspected before choosing the adapter?

Human input needed: provide the project/repository URL (and API documentation if separate). Do not paste credentials. If private access is required, identify the approved access mechanism. The investigator should then inspect request/response schemas, local versus hosted execution, licensing, reproducibility controls, identifiers, output formats, limits, and failures. No live generation is needed for this decision prerequisite.

The user said they would send the project; its identity is currently unknown. Recommended input is the same Synthea patient/encounter history that feeds PostgreSQL, with provenance preserved. Resolution records the actual contract and example location, not an invented API.
