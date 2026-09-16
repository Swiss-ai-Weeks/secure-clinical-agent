# Define patient identity, linkage, and source provenance

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: 02, 03

## Question

How will one opaque patient_key consistently join flattened FHIR, generated notes, chunks, and grants across retries without exposing source identifiers?

Decide source-ID/reference normalization (including fullUrl and urn:uuid references), identity namespace, pseudonym strategy, document/source-resource IDs, and resource/version provenance. Specify whether a reversible mapping is necessary for synthetic data, where it lives, who can read it, and how it survives restarts; OpenBao is presently a dev-mode service on an isolated network.

Resolve the distinction between de-identification/pseudonymization and irreversible anonymization. Decide how birth year, dates, rare clinical details, and longitudinal time relationships are treated consistently across both branches. A stable linkage key means the working dataset should not be casually described as irreversibly anonymous.
