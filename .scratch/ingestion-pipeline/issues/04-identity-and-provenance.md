# Define patient identity, linkage, and source provenance

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Codex
Blocked by: 02, 03

## Question

How will one opaque patient_key consistently join flattened FHIR, generated notes, chunks, and grants across retries without exposing source identifiers?

Decide source-ID/reference normalization (including fullUrl and urn:uuid references), identity namespace, pseudonym strategy, document/source-resource IDs, and resource/version provenance. Specify whether a reversible mapping is necessary for synthetic data, where it lives, who can read it, and how it survives restarts; OpenBao is presently a dev-mode service on an isolated network.

Resolve the distinction between de-identification/pseudonymization and irreversible anonymization. Decide how birth year, dates, rare clinical details, and longitudinal time relationships are treated consistently across both branches. A stable linkage key means the working dataset should not be casually described as irreversibly anonymous.

## Comments

### Investigation and first decision round — 2026-09-17

Read-only inspection found that all 10 smoke patients and their 500 note document IDs occur in the seed; the corresponding patient bundles are byte-identical. The two source manifest contracts differ in profile/population. The worker's batch identity also includes worker/configuration inputs, so it must not be assumed to define durable patient identity. The source worker validates source linkage but has no opaque identity adapter.

The maintained deployment config declares OpenBao in dev mode without a storage volume; it is not an existing durable identity registry. A separate restricted mapping/provenance facility has not been implemented. Notes contain embedded event dates and ages, so privacy/date handling must agree across structured records and narrative.

Implementation constraints from inspection: the [source worker](../../../backend/ingestion/worker.py) resolves exact bundle `fullUrl` and `ResourceType/id` aliases, rejects missing/ambiguous references, and does not fetch external references. It checks patient subjects and note encounter links, but preparation must additionally validate Condition/Observation encounter references and their patient ownership. The [current SQL schema](../../../backend/deploy/patient360/sql/fhir/01-init.sql) accepts text patient keys and birth years but lacks source-identity uniqueness/provenance fields; clinical table migrations belong to the projection ticket.

The following proposals are presented for human decision, not approved contracts:

- Keep the same opaque patient identity for the same source patient across smoke/seed, retries, and downstream reprocessing. Give distinct source datasets explicit namespaces; never infer that two patients match from name or demographics. Keep document/encounter/resource identity distinct from content revisions and preparation versions.
- Retain a restricted source-to-opaque mapping and detailed provenance locally for the worker/operator, outside searchable stores and ordinary logs; preserve this state across restarts. Expose only safe opaque citations to authorized application users. Local backup/recovery is needed; do not rely on dev-mode OpenBao for durable linkage.
- For this synthetic-only demonstration, preserve clinical event dates/times and intervals, retain birth year/age rather than full birth date, and apply the same rule to note text and structured fields. Date shifting remains an alternative for discussion.
- Preserve clinical diagnoses, codes, values, units, and rare clinical details needed for the demonstration while removing personal/contact identifiers. Call the result pseudonymized synthetic data; retained linkage is not a guarantee of irreversible anonymization.

Keep this ticket claimed pending the user's answers. These choices do not resolve the detailed structured-field projection, sanitization recognizers, or grant model.

### User answers and birth-date question — 2026-09-17

- Q1: the user accepted stable identities and asked what a smoke patient means. Clarified that the smoke fixture is the 10-patient quick-check subset of the 100-patient seed, not a clinical category; the same source patient retains its opaque key across those batches and reprocessing.
- Q2: the user approved retraceability to source records. Retain the proposed restricted persistent mapping/provenance for worker/operator use and safe opaque application citations.
- Q3: the user wants to preserve the synthetic data's realism and asked how much additional work retaining full birth dates would require. **Birth-date precision remains open**; do not record approval of either year-only or full-date output yet. No date-shifting implementation is authorized by this exchange.
- Q4: the user approved preserving clinical details while removing personal/contact identifiers, with pseudonymized synthetic data as the description.

The next question is whether this synthetic-only demo should retain the generated full birth dates in prepared structured records and, if present, note text. This is a policy choice for downstream prepared data; raw source artifacts already retain their original fields and remain unchanged.

Read-only follow-up found full `YYYY-MM-DD` Patient.birthDate values for all 100 seed patients. The pinned Synthea note template emits an encounter date and age (years, months, or newborn), not a birth-date field. Retaining full birth dates needs no source regeneration. Compared with the existing `birth_year` SQL field, the expected additional work is a date-column migration, explicit Patient projection, date validation/age-consistency checks, and an explicit synthetic-demo retention policy. The refined recommendation is to retain full synthetic birth dates in authorized structured patient records without adding them to note text or embedding payloads; user confirmation is pending.

## Answer

Resolved 2026-09-17 after the user accepted the revised birth-date recommendation. The earlier pending proposals above are discussion history; this resolution is the current contract.

### Approved behavior

- **Identity continuity:** the same source patient keeps one opaque patient key across smoke/seed batches, retries, and downstream reprocessing. Reuse that key in structured records, notes, chunks, and grants. Unrelated source datasets use separate explicit namespaces; matching demographics do not establish identity.
- **Traceability:** retain persistent restricted mappings and detailed provenance for the ingestion worker and authorized operator. Keep them outside searchable clinical stores, embedding requests, ordinary logs, and application citations. Application users receive authorized opaque citations, not source identifiers or raw file paths. Preserve the mapping state across restarts and back it up with the restricted source data; dev-mode OpenBao is not the durable store.
- **Dates and demographics:** preserve synthetic clinical event dates/times, intervals, and ages. Retain full generated birth dates in authorized structured patient records. Do not add birth dates to note text, embedding requests, or vector metadata. Existing source notes contain event dates and ages, not an explicit birth-date field. Full birth-date retention supersedes the original year-only proposal and requires no source regeneration.
- **Clinical meaning:** preserve diagnoses, codes, measurements, units, and rare clinical details needed for the demonstration while removing personal/contact identifiers. This is a pseudonymized synthetic dataset, not a claim of irreversible anonymity or a policy for real patient data.

### Implementation defaults for that behavior

- Use a persistent source-to-opaque registry: allocate an opaque UUID once per `(source namespace, resource type, source ID)` and reuse it on subsequent imports. Enforce unique mappings and atomic updates. Identical smoke/seed resources share the namespace and mapping. Namespace identity must not depend on batch ID, population profile, worker digest, sanitization version, or embedding model. Treat a distinct source lineage as a new namespace unless continuity is explicitly established.
- Patient, encounter, document, and source-resource identities are separate registry entries. Track source versions/content digests and preparation-policy versions separately from logical identity; changed content does not silently create a different patient. Chunk identity and replacement rules remain in the chunking/vector decisions.
- Resolve exact bundle `fullUrl` and `ResourceType/id` aliases, including indexed `urn:uuid:` references. Do not infer identity by URL suffix, demographics, or external lookups. Reject missing, ambiguous, cross-patient, and unsupported references before preparation. Validate Condition/Observation encounter ownership in addition to the source worker's existing subject and note-link checks. Contained or unindexed versioned/external references remain unsupported for this first source adapter.
- Restricted provenance records namespace, source IDs, bundle path/hash, batch ID, resource version/content digest, and patient/encounter/document links. Prepared artifacts retain opaque linkage and processing-version evidence. Store local registry/provenance state outside immutable source batches with owner-restricted permissions; choose the concrete file/database layout during implementation. Missing/corrupt registry state for an existing namespace must fail preparation until restored, not silently assign new identities. A second machine must restore this state to preserve opaque keys; source regeneration alone is insufficient.

Required implementation checks: stable keys across smoke/seed and replay; distinct namespace/resource identities; invalid/cross-patient reference rejection; registry restart and backup/restore behavior; traceability from opaque citations; no raw source IDs in prepared/search artifacts or logs; preservation of structured synthetic birth dates and clinical dates/ages without adding DOB to embedding payloads. These checks are requirements, not tests already run.

The identity/provenance decision is complete; the adapter, registry, migrations, sanitization, and store publication are not implemented by this resolution. [Choose the FHIR-to-PostgreSQL projection and update rules](05-fhir-projection.md) owns the safe field projection and existing-volume migration; [Choose note de-identification and chunk boundaries](07-deid-and-chunking.md) owns recognizers, note handling, and chunking under this policy.
