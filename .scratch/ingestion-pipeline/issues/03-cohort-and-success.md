# Choose the first cohort and ingestion success criteria

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: none

## Question

What reproducible synthetic cohort and demonstration are sufficient for the first ingestion milestone?

Approved patient counts: 10 patients for smoke checks, then 100 patients for the initial seed (user confirmation, 2026-09-17). Remaining proposal for discussion: batch-only execution first; Patient, Condition, and Observation as the first structured resource set; linked clinical notes generated from those same patients. Confirm note types, language, time window, number of notes, and whether adverse/prompt-injection examples belong in a separately labelled evaluation set.

Set a fixed generator version, seed, reference date, configuration, and a manifest of actual generated counts (including any extra/deceased records). Define expectations for two principals with different patient access, repeat runs, and clinical consistency. Determine whether the initial target is a development demo or a stricter production design. The count approval does not resolve the remaining choices; this ticket stays open.

## Partial decision — 2026-09-17

The user approved 10 smoke patients and 100 seed patients when reviewing GitHub issue #3. The user also confirmed acceptance scenarios at the seed-scope and generator-contract handoff boundary. No generator URL or remaining cohort choices were supplied. [Acceptance scenarios](../../../backend/ingestion/tests/issue-01-handoff.feature) capture the handoff requirements; no pipeline implementation or dataset generation followed this decision.
