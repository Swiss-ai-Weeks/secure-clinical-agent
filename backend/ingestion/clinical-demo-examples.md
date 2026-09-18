# Source-grounded clinical demonstration examples

These three examples were selected from the verified 100-patient Synthea seed and approved by the user on 2026-09-17 in [Choose the first cohort and ingestion success criteria](../../.scratch/ingestion-pipeline/issues/03-cohort-and-success.md#answer). They are synthetic retrieval examples, not clinical recommendations or evidence that search is implemented.

## Approved demonstrations

| Example | Suggested note-search query | Expected note evidence | Structured evidence to display alongside the note |
| --- | --- | --- | --- |
| Diabetes self-management | Find an encounter note documenting type 2 diabetes and its self-management plan. | The selected note names type 2 diabetes and a diabetes self-management plan. | Same-patient, same-encounter HbA1c: **6.98%**. |
| Hypertension education | Find an encounter note documenting essential hypertension and lifestyle education. | The selected note names essential hypertension and lifestyle education regarding hypertension. | Same-patient, same-encounter blood pressure: **143/89 mm[Hg]**. |
| Historical pneumonia encounter | Find an encounter note documenting pneumonia with hypoxemia and oxygen administered by mask. | The selected note names pneumonia, hypoxemia, respiratory distress, and oxygen administration by mask. | Same-patient, same-encounter oxygen saturation: **87.4%**; respiratory rate: **25.905/min**. |

Each example uses a different synthetic patient. The diagnoses come from explicit Condition records, not inference from measurements. Display source values without presenting them as treatment advice or inventing missing clinical facts.

The pneumonia Condition is marked **resolved** in the exported record. Present this as a historical encounter, not a current illness. Multiple measurements occur during that encounter; the chosen observations share a timestamp and are specific source fixtures, not claims about the latest measurement. The restricted evidence records the timestamps for all three examples.

## What these examples exercise

For each example, retrieve the sanitized encounter note for diagnosis/care context, then show the linked safe structured Observation values through an authorized read. These template notes omit the selected measured values: a note-only vector search cannot prove retrieval of those values. Cite the note for its narrative and the Observation for its measurement separately. A result that attributes an absent numeric measurement to the note fails the evidence check.

The selected source document is an expected relevant result, not a promise that it is the only relevant match or ranks first. A patient may have multiple similar notes. Exact top-k/ranking thresholds and the public query interface remain later acceptance decisions. If chunking separates relevant sections, use authorized chunks from the same document with correct lineage.

Approved access demonstration: use the same query with one principal granted access to the selected patient and another without access, then revoke the first grant and repeat. Only the granted principal may receive that patient's note or structured evidence; the other principal can still receive independently authorized results. Caller-supplied patient filters may only narrow access. Grant-model implementation remains a separate decision.

## Local source evidence

Source batch: `71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36`. The worker's `verify` command passed again with 100 patients and 4,645 notes. This is a `source_ready` batch, still unsanitized and unpublished.

The [restricted source evidence](../../.data/clinical-demo/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36/candidate-evidence.json) records exact source bundle paths, resource IDs, raw-note line numbers, hashes, clinical-only excerpts, and linkage checks. It is a local ignored artifact and will not exist in a fresh checkout until recreated from the corresponding seed. Its filename retains its original candidate-selection name; the decision ticket records approval. Source identifiers in that report are fixture locators, not the future public patient/document identity contract. No source batch artifacts were changed.

Preserve the association between these source fixtures and future opaque IDs when implementing preparation. After sanitization, recheck that diagnosis/care context, numeric values, units, and patient/encounter linkage survive before using the examples as end-to-end acceptance evidence. Apply the [amended identity/date policy](../../.scratch/ingestion-pipeline/issues/04-identity-and-provenance.md#answer): birth year only and temporary internal source resource IDs. Detailed sanitization, safe field projection, grants, and publication remain downstream work.

## Structured database verification — 2026-09-18

The three examples now pass independent source-to-PostgreSQL checks: HbA1c **6.98%**, blood pressure **143/89 mm[Hg]**, oxygen saturation **87.4%**, and respiratory rate **25.905/min**. Patient/encounter ownership, parent/component links, codes, units, event timestamps and raw document lineage match the selected source fixtures. The historical pneumonia diagnoses remain **resolved**. See [structured validation](structured-validation.md) and the [restricted example results](../../.data/structured-acceptance-20260918/clinical-examples.json).

This verifies structured storage and restricted source lineage. Notes remain unsanitized and unloaded; authorized retrieval and its allow/deny/revocation demonstration remain outstanding.
