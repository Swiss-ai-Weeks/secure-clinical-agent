# Define clinically linked synthetic-note generation

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: 01, 03, 04

## Question

How will the supplied generator turn selected Synthea histories into notes with stable patient/document provenance and no unsupported clinical claims?

Choose the input patient/encounter projection, note types, language, date rules, source references, generation configuration/version recording, and acceptance/rejection criteria. Decide whether it runs locally or calls an external endpoint, what synthetic data may cross that boundary, and how failed/rate-limited generation resumes.

Keep generated notes distinct from source FHIR facts. Decide how generated contradictions, unknown patient links, and explicit prompt-injection fixtures are labelled and quarantined. Do not promote invented narrative facts into structured clinical truth.
