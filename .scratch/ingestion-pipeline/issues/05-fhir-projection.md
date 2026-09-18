# Choose the FHIR-to-PostgreSQL projection and update rules

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Codex
Blocked by: 04

## Question

How should Synthea FHIR R4 populate the existing patients, conditions, and observations tables while preserving useful clinical meaning and removing identifiers?

Specify reference resolution, coding/system selection, numeric/text/component observations, units, clinical/status fields, dates, unsupported resources, and invalid/missing references. Decide whether additional resources require later schema migrations.

Main's schema now has top-level resource JSONB allowlists, source uniqueness, component observations, and patient-scoped foreign keys. Specify the nested safe projection and omissions rather than passing raw objects through those allowlists; flattening alone is not de-identification. Use its temporarily approved raw non-patient `source_id` upsert keys within the agreed source namespace and define update/delete handling. The user approved a backed-up volume replacement for this demo bootstrap; worker retries must not reset the database. Link acceptance examples to the resolved cohort.

## Comments

### Resolved identity and date policy — 2026-09-17

Apply the amended [Define patient identity, linkage, and source provenance](04-identity-and-provenance.md#answer): birth year only, opaque patient keys, temporary raw non-patient source resource IDs, and preserved clinical event dates/times. No full-DOB column migration is required. Keep full DOB out of prepared records, note enrichment, and embedding/vector payloads. Field allowlists, coding/component representation, and source update/delete behavior remain this ticket's decisions.

### Main schema imported — 2026-09-17

[Main schema integration checkpoint](../../../backend/ingestion/schema-integration.md) records the imported schema, the user's reconciliation choices, and runtime validation. Birth-date precision, temporary source-ID storage, and volume replacement are now decided. Key representation, nested projection, labels, and update/delete semantics still need adapter work. [Move source resource identifiers into restricted provenance](12-restrict-source-resource-identifiers.md) tracks the explicitly deferred source-ID restriction.

## Answer

Resolved 2026-09-18 after the user answered yes to all three policy questions and instructed: "Do what you can do." This confirms strict projection and missing-value handling, stable upserts with removals rejected, and reviewed fixture label lists that block unknown codes. The earlier dry-run checkpoint is historical; committed execution evidence is recorded in [structured validation](../../../backend/ingestion/structured-validation.md).

### Approved contract

- Scope: Patient, minimum Encounter linkage, Condition and Observation, including component rows. Other resource types are counted as skipped. DocumentReference receives a restricted opaque identity and encounter provenance but no note row/text is loaded. No schema migration is needed for this scope.
- References: exact indexed `fullUrl`/`ResourceType/id` aliases only, with resource-type and patient ownership checks. Missing optional encounters become NULL; present broken/wrong-type/cross-patient links fail the entire preparation. No suffix guessing, external fetching or demographic matching.
- Identity: restricted persistent SQLite registry at `.data/identity/registry.sqlite`, namespace `patient360-synthea-demo-v1`. Patient keys are random `p_` plus UUID hex; resource UUIDs and opaque citation IDs remain stable across smoke, seed, restart and changed-content updates. Explicit initialization requires an empty clinical patient table. Missing/corrupt registry state requires restoration; backup uses SQLite's backup API. The importer accepts only the checked-in source-generation configuration in this namespace.
- Missing values: optional columns are NULL, without invented zero, dates or status. Observation code/system/status and Encounter status/class are mandatory. The schema's nonnullable deceased flag remains false when the source omits it; projected JSON preserves that source absence. Unsupported value choices, ambiguous components, invalid dates/intervals, nonfinite numbers, unknown codes and unreviewed source security labels fail preparation. No partial failed batch is loaded.
- Patient: gender, birth year, deceased flag and deceased year only. Patient JSONB contains year-only dates. Names, identifiers, address, contact fields, extensions and source patient IDs never enter prepared clinical records.
- Clinical coding: prefer SNOMED for Condition and Encounter scalar fields and LOINC for Observation; retain source order within a preferred system and preserve safe alternate codings in JSON. Reviewed ICD-10/SNOMED/other fixture codings remain usable as fallbacks. All display strings come from the checked-in dictionary, never the incoming display/text. Preserve the source's synthetic/local codes without claiming terminology-authority validation.
- Dates: retain clinical event timestamps in nested JSON, flatten Condition dates to source calendar dates and Encounter/Observation timestamps to timestamp columns. Absent optional dates stay NULL. Reject unsupported partial event dates and reversed intervals. Do not shift dates.
- Observations: preserve numeric, integer, boolean and coded values, including zero/false. Units use the reviewed quantity code, falling back to a reviewed unit if no code exists; truly absent units remain NULL. Reject comparators until a representation is chosen. Preserve six exact fixture text values (culture results, CABG descriptions, elective/urgent); other valueString text is omitted and counted until sanitization exists. Project numeric reference bounds; omit/count unsanitized range text. Missing values stay NULL; dataAbsentReason is counted, with no fabricated value.
- Components: keep an opaque parent row and one child per accepted component, with stable internal upsert suffix `#componentCode`. Reject repeated component codes even across systems. Child rows inherit parent baseline labels; parent JSON contains only projected components and takes the maximum/union of their labels.
- Code-aware omissions: exclude LOINC Address `56799-0`, Race `32624-9`, Hispanic/Latino `56051-6`, and Preferred language `54899-0` from both rows and parent JSON. The seed contains 1,027 instances of each. Generic field-name filtering would otherwise leak street addresses through `valueString`.
- Labels: [labels.yaml](../../../backend/ingestion/labels.yaml) is a versioned JSON-syntax YAML dictionary of 605 reviewed fixture concepts, fixed displays, exact text values and units. Apply the repository's explicit sensitive-code rules to **all retained coding fields**, including encounter reasons and coded Observation results. Combine confidentiality by N < R < V and sensitivity by sorted union. Unknown codes fail rather than silently becoming normal. Nonspecific immune, cognitive, psychosocial and safety concepts receive conservative R without inventing a diagnostic sensitivity tag. This is bounded synthetic-fixture coverage, not a SNOMED closure or production classifier.
- Updates: upsert by opaque patient key / temporary internal non-patient source_id. Keep internal UUID/citation/ownership fixed; update changed scalar fields, nested JSON and labels, including clearing newly absent optional values. Identical rows cause no UPDATE and preserve timestamps. Treat each included patient's bundle as a complete snapshot: an existing resource or component missing from that patient's new projection aborts the import. Patients absent from a batch are untouched, so replaying smoke after seed does not delete seed patients. No clinical DELETE, volume reset or privilege expansion occurs.
- Writes: worker-role transaction, advisory lock, staged rows, ownership checks, stable upserts, comparison of every projected field, and an audit ingest event. Failure rolls back the entire transaction. PostgreSQL error details are suppressed because they can include source rows. Prepared artifacts and manifests are versioned separately from immutable source; CLI output contains aggregate counts and opaque batch paths only. Structured loading does not establish cross-store publication or authorize reads.

#### Implementation assets and validation

[Structured CLI](../../../backend/ingestion/structured.py), [identity registry](../../../backend/ingestion/identity.py), [projection](../../../backend/ingestion/projection.py), [PostgreSQL adapter](../../../backend/ingestion/postgres.py), and [validation evidence](../../../backend/ingestion/structured-validation.md).

The implementation tests cover identity restart/backup, identifier canaries, nested omissions, numeric/component fidelity, coding selection, reference rejection, labels, missing values, stable updates and duplicate-free replay. Live worker-role tests use rolled-back transactions. The user has authorized committed smoke, duplicate-free smoke replay, and then seed loading. Record their runtime evidence separately; the policy resolution alone does not establish a completed load.

### Execution follow-up — 2026-09-18

The smoke import and its zero-change replay passed before the 100-patient seed was committed. The full-seed replay exposed an unindexed staging anti-join that exceeded the statement timeout. Adding unique staging-key indexes and planner statistics fixed the query without altering clinical data or increasing timeouts. A 12,000-row importer regression now covers this path; all 40 tests pass. Final replay, identity, clinical-example and backup evidence is recorded in [structured validation](../../../backend/ingestion/structured-validation.md).
