# Choose the first cohort and ingestion success criteria

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Codex
Blocked by: none

## Question

What reproducible synthetic cohort and demonstration are sufficient for the first ingestion milestone?

Approved patient counts: 10 patients for smoke checks, then 100 patients for the initial seed (user confirmation, 2026-09-17). Remaining proposal for discussion: batch-only execution first; Patient, Condition, and Observation as the first structured resource set; linked clinical notes generated from those same patients. Confirm note types, language, time window, number of notes, and whether adverse/prompt-injection examples belong in a separately labelled evaluation set.

Set a fixed generator version, seed, reference date, configuration, and a manifest of actual generated counts (including any extra/deceased records). Define expectations for two principals with different patient access, repeat runs, and clinical consistency. Determine whether the initial target is a development demo or a stricter production design. The historical discussion below records how the choices were settled; the final resolution is in Answer.

## Partial decision — 2026-09-17

The user approved 10 smoke patients and 100 seed patients when reviewing GitHub issue #3. The user also confirmed acceptance scenarios at the seed-scope and generator-contract handoff boundary. No generator URL or remaining cohort choices were supplied. [Acceptance scenarios](../../../backend/ingestion/tests/issue-01-handoff.feature) capture the handoff requirements; no pipeline implementation or dataset generation followed this decision.

## Comments

### Cohort choices confirmed — 2026-09-17

The user answered the wayfinder question round:

- Q1: approved Massachusetts, English Synthea encounter notes, reference/end date 2026-09-01, ten years of exported history, and retaining all generated encounter notes with actual counts recorded. The existing source contract supplies template History and Physical / Evaluation and Plan notes. Previously approved targets remain 10 smoke patients and 100 seed patients.
- Q2: approved batch-first ingestion for a development demo, projecting Patient, Condition, and Observation plus linked notes. Exact safe fields remain the separate projection decision.
- Q3: requested that the agent find concrete source-grounded clinical demonstration examples. Example selection is being grounded in the verified seed; clinical scenarios have not yet been confirmed by the user.
- Q4: approved a small, separately labelled synthetic prompt-injection evaluation corpus kept separate from the clinical seed. Fixture design and expected security behavior still need specification; no such corpus has been generated.

Seed verification rerun successfully with the worker's `verify` command: batch `71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36`, 100 patients and 4,645 notes, status `source_ready`. This establishes source integrity and lineage, not downstream sanitization, publication, or retrieval readiness.

### Clinical examples proposed — 2026-09-17

[Source-grounded clinical demonstration candidates](../../../backend/ingestion/clinical-demo-examples.md) supplies three concrete examples: diabetes self-management, hypertension education, and a historical pneumonia encounter. Each has explicit Condition evidence, measured Observations, and a matching patient/encounter note. Exact locators and independent linkage/value assertions are retained in the restricted evidence linked from that document. Numeric measurements are absent from the selected notes, so the demonstration needs separate citations for note narrative and structured observations; note-only vector retrieval cannot establish measurement fidelity.

The candidate examples and allow/deny/revocation demonstration are presented for user confirmation. Keep this ticket claimed until that exchange completes. No retrieval results, sanitized artifacts, or adversarial fixtures have been produced.

## Answer

Resolved 2026-09-17 after the user confirmed the proposed demonstration set: "Yes this dataset seems perfect, let's go with that."

- **Cohort and milestone:** a batch-first development demo with 10 smoke patients followed by a 100-patient clinical seed. Use Massachusetts, English Synthea template encounter notes (History and Physical / Evaluation and Plan), reference/end date 2026-09-01, and ten years of exported history. Retain all generated encounter notes and report actual patient/resource/note counts, including any extra/deceased records, rather than treating target counts as evidence.
- **Reproducibility:** retain the existing [pinned configuration](../../../backend/ingestion/config/synthea.json): Synthea 4.0.0, population seed 360, clinician seed 361, artifact/runtime digests, and fixed export settings. Verify manifests and reuse intact source batches on replay; changing the contract creates a different batch. Existing verification evidence is source-stage evidence only.
- **Resource scope:** Patient, Condition, and Observation with linked notes from the same synthetic patients. Exact safe structured fields and source-update behavior remain in [Choose the FHIR-to-PostgreSQL projection and update rules](05-fhir-projection.md).
- **Clinical demonstration:** approve the three [source-grounded clinical demonstration examples](../../../backend/ingestion/clinical-demo-examples.md): diabetes self-management, hypertension education, and historical pneumonia. That linked asset holds the exact queries, measured values, and evidence locators. Preserve the distinction between note narrative and structured measurements, and do not present resolved pneumonia as a current illness.
- **Access demonstration:** run the same query with one principal granted access to the selected patient and another without access, then revoke the first grant and repeat. The unauthorized/revoked principal must receive no note text or structured evidence for that patient; independently authorized results may still appear. Patient filters can only narrow authorized scope. Detailed grant semantics and enforcement remain in [Define grants, chunk ACL metadata, and retrieval enforcement](08-grants-and-acl.md).
- **Adversarial evaluation:** include a small, separately labelled synthetic prompt-injection corpus, separate from the clinical seed. Its fixture design and handling remain in [Define clinically linked synthetic-note generation](06-note-generation-contract.md); approval does not mean the corpus exists.

The cohort decision is complete. Identity, sanitization, safe projection, authorization, vector storage, publication, and runtime retrieval acceptance remain separate open decisions. No production readiness, successful retrieval, or GitHub implementation-issue completion is implied.
