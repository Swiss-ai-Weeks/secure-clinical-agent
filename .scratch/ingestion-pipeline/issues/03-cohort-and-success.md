# Choose the first cohort and ingestion success criteria

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: none

## Question

What reproducible synthetic cohort and demonstration are sufficient for the first ingestion milestone?

Proposal for discussion: 10 patients for smoke checks, then 100 patients for the initial seed; batch-only execution first; Patient, Condition, and Observation as the first structured resource set; linked clinical notes generated from those same patients. Confirm note types, language, time window, number of notes, and whether adverse/prompt-injection examples belong in a separately labelled evaluation set.

Set a fixed generator version, seed, reference date, configuration, and a manifest of actual generated counts (including any extra/deceased records). Define expectations for two principals with different patient access, repeat runs, and clinical consistency. Determine whether the initial target is a development demo or a stricter production design. Proposed numbers are not yet a human-approved decision.
