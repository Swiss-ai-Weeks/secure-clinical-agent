# Patient360 — FHIR Resource Plan

Companion to [Patient360-Build-Plan.md](Patient360-Build-Plan.md). This is the contract between ingestion (Track B), the tools and PDP (Track A), and the frontend types (Track D): which FHIR resources come in, exactly which elements survive, how they are labelled, which tables they land in, which tool exposes them, and which resources we emit.

**FHIR version pin:** ingest **R4 (4.0.1)** as produced by Synthea with US Core 6.1.0 profiles. Emit **R4** by default; R5 renames are a mapping table, not a second code path. Nothing here requires R5 or R6.

**Ingestion alignment, 2026-09-17:** the user adopted this schema's birth-year-only representation and temporarily approved raw non-patient `source_id` values for internal upserts. Patient keys and application citations remain opaque. [Move source resource identifiers into restricted provenance](../.scratch/ingestion-pipeline/issues/12-restrict-source-resource-identifiers.md) tracks the required follow-up; until then, the first importer stays within the agreed source namespace. [Schema integration evidence](../backend/ingestion/schema-integration.md) records the backed-up demo database rebuild and distinguishes initialized tables from completed ingestion.

---

## 1. Principles

1. **Allowlist, not blocklist.** Each resource has an explicit list of elements that are projected. Anything not listed is dropped, including `text` (narrative), `extension[]`, `identifier[]`, `contained[]`, and `meta` beyond `profile`. Tests assert the projected JSONB contains only allowlisted keys.
2. **One opaque key.** `Patient.id` from the bundle is exchanged for a random `p_xxx` via the vault at the start of each bundle; every other resource's `subject`/`patient` reference is rewritten to that key during bundle-aware reference resolution. Unresolvable patient references quarantine the resource.
3. **Deterministic source ids.** `source_id = "{resourceType}/{id}"` from the bundle, unique per table, so re-running a batch upserts instead of duplicating. Citation ids shown to the agent are our own short random ids (`cite_id`, e.g. `obs_7f3a9c21d0e4`, `note_c21d0e44a9f1`; twelve hex characters = 48 bits, because 32 bits has a 50% collision chance at ~65k rows and one Synthea observations table exceeds that), never `source_id`, never sequential.
4. **Labels at ingest.** Every clinical row gets an HL7 HCS label: `confidentiality ∈ {N, R, V}` and `sensitivity[]` from the v3 `ActCode` sensitivity codes. Default `N`. Assignment is by code list in `backend/ingestion/labels.yaml`, never by free text.
5. **Quasi-identifiers are flagged, not deleted.** `birth_year`, `sex`, exact dates, and `deceased_year` are classed `quasi_identifier` in `clinical.column_policy` (with `aggregate_dim` marking the columns the researcher path may group by) so the aggregate path and output rails treat them differently from clinical values.
6. **Unknown resource types are skipped and counted** in the run manifest, never fatal.

### HCS codes used

| Purpose | Code system | Codes we use |
|---|---|---|
| Confidentiality | `http://terminology.hl7.org/CodeSystem/v3-Confidentiality` | `N` normal, `R` restricted, `V` very restricted |
| Sensitivity | `http://terminology.hl7.org/CodeSystem/v3-ActCode` (InformationSensitivityPolicy) | `PSY` psychiatry, `ETH` substance abuse, `HIV`, `STD`, `SEX` sexuality and reproductive health, `GDIS` genetic disease, `SDV` sexual assault / domestic violence |
| Obligations | `v3-ActCode` (ObligationPolicy) | `REDACT`, `NOAUTH` |
| Purpose of use | `v3-ActReason` (PurposeOfUse) | `TREAT`, `HRESCH`, `BTG`, `PATRQT`, `HOPERAT` |

Note: the v3 code for substance-use sensitivity is **`ETH`**, not `SUD`. Earlier drafts used `SUD`; `ETH` is correct.

---

## 2. Ingested resources

**Schema conventions as built** (`backend/deploy/patient360/sql/fhir/`, schema `clinical`):

- Every coded element is a triple `code`, `code_system`, `display` (a Coding without its `system` is rejected by CHECK). The tables below name the `code` column; the `_system` and `_display` siblings are implied.
- Every clinical row carries `id` (uuid), `cite_id` (short random id shown to the agent, e.g. `obs_7f3a9c21d0e4`), `source_id` (`{resourceType}/{id}`, unique), `patient_key`, `encounter_id`, `confidentiality`, `sensitivity[]`, `resource` (projected JSONB).
- Every reference between clinical rows (`encounter_id`, `parent_id`, `reason_condition_id`, `study_id`, and both sides of `diagnostic_report_results`) is a composite foreign key that carries `patient_key`, so a row can only reference rows of the same patient; a cross-patient link is rejected by the database. Batch provenance (the run manifest and reproducibility pins) is the `detail` of the `ingest` row in `audit.audit_events`, not a clinical table or column.
- The `resource` JSONB allowlist is a CHECK constraint per table; `resourceType` is always permitted alongside the listed elements.
- Value sets are named functions, one per FHIR value set (`clinical.vs_observation_status()`, `clinical.vs_request_intent()`, `clinical.vs_confidentiality()`, ...; `identity.vs_user_role()`; `audit.vs_purpose_of_use()`, ...), each returning `text[]` and carrying the FHIR canonical URL and binding strength in its `COMMENT`. Column CHECKs reference them (`status = ANY (clinical.vs_observation_status())`), so each list exists once, is shared where FHIR shares it, and the worker can read the same list with `SELECT clinical.vs_observation_status()`. `MedicationRequest.intent` and `NutritionOrder.intent` deliberately use different sets, as in FHIR.
- `DiagnosticReport` lands in one table `diagnostic_reports`; `imaging_reports` is a view over it (`category <> 'LAB'`).

### 2.1 `Patient` → `patients`

| Element | Action | Target |
|---|---|---|
| `id` | exchange for random `p_xxx` via vault; original id → vault only | `patient_key` |
| `gender` | keep (administrative gender) | `sex` |
| `birthDate` | **year only**; ages ≥ 90 reported as `90+` at read time | `birth_year` (quasi-identifier) |
| `deceasedBoolean` / `deceasedDateTime` | boolean + year | `deceased`, `deceased_year` |
| `name`, `telecom`, `address` (incl. geolocation extension), `photo`, `contact`, `communication`, `maritalStatus`, `multipleBirth*`, `generalPractitioner`, `managingOrganization`, `link` | **drop** | — |
| `identifier[]` (Synthea UUID, MRN, SSN, DL, passport) | **drop**; MRN → vault only | — |
| `extension`: `us-core-race`, `us-core-ethnicity`, `us-core-tribal-affiliation`, `us-core-birthsex`, `us-core-sex`, `us-core-genderIdentity`, `patient-birthPlace`, `patient-mothersMaidenName`, `*-life-years` | **drop** (race/ethnicity and gender identity are GDPR Art. 9 special categories) | — |
| `text` (narrative contains name) | **drop** | — |

Label: `N`. Projected JSONB = `{resourceType, gender, birthDate, deceasedBoolean | deceasedDateTime}` only, with `birthDate` and `deceasedDateTime` at year precision (`"1979"`; FHIR `date`/`dateTime` allow `YYYY`, so the object stays valid FHIR). The table CHECK rejects any other key and any date with more than year precision. `patients` has no `source_id`: the source `Patient.id` exists only in the vault.

### 2.2 `Encounter` → `encounters`

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `status` | keep | `status` |
| `class.code` (`AMB`, `EMER`, `IMP`, `ACUTE`, `NONAC`, `OBSENC`, `PRENC`, `SS`, `VR`) | keep | `class` |
| `type[0].coding` (SNOMED) | keep code + display | `type_code`, `type_display` |
| `period.start`, `period.end` | keep (quasi-identifier) | `started_at`, `ended_at` |
| `reasonCode[]` (SNOMED) | keep first | `reason_code`, `reason_display` |
| `subject` | rewrite to `patient_key` | `patient_key` |
| `participant[]`, `serviceProvider`, `location[]`, `hospitalization`, `identifier[]` | **drop**; replace with department tag from a static mapping of Synthea `serviceProvider` → `dept` | `dept` |

Label: `N`; `R` + `PSY` if `type_code` is a psychiatric encounter type (code list).

### 2.3 `Condition` → `conditions`

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `code.coding` (SNOMED) | keep | `code`, `display` |
| `clinicalStatus`, `verificationStatus` | keep code | `clinical_status`, `verification_status` |
| `category[]` (`problem-list-item`, `encounter-diagnosis`) | keep | `category` |
| `onsetDateTime`, `abatementDateTime`, `recordedDate` | keep (quasi-identifier) | `onset_date`, `abatement_date`, `recorded_date` |
| `subject`, `encounter` | rewrite | `patient_key`, `encounter_id` |
| `asserter`, `recorder`, `evidence`, `note`, `stage`, `identifier` | drop | — |

Label by SNOMED subsumption / code list:
- descendants of 74732009 *Mental disorder* → `R` + `PSY`
- substance-related disorders (e.g. 66214007, 7200002, 191816009) → `R` + `ETH`
- 86406008 *HIV infection* and descendants → `V` + `HIV`
- STIs (e.g. 76272004, 15628003, 240589008) → `R` + `STD`
- genetic disorders (e.g. 190905008 cystic fibrosis, 417357006 sickle cell) → `R` + `GDIS`
- pregnancy and reproductive (e.g. 72892002, 47200007) → `N` + `SEX` (sensitivity tag without raising confidentiality)

### 2.4 `Observation` → `observations`

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `status` | keep | `status` |
| `category[0].coding.code` (`vital-signs`, `laboratory`, `survey`, `social-history`, `exam`, `imaging`, `procedure`) | keep | `category` |
| `code.coding` (LOINC) | keep | `code`, `display` |
| `effectiveDateTime` / `effectivePeriod.start`, `issued` | keep (quasi-identifier) | `effective_at`, `issued_at` |
| `valueQuantity.value/.unit`, `valueCodeableConcept.coding[0]`, `valueString`, `valueBoolean`, `valueInteger` | keep the one present | `value_num`, `unit`, `value_code`, `value_text` |
| `component[]` (blood pressure, panels) | flatten to child rows with `parent_id` | `observations` rows with `parent_id`, `component_code` |
| `interpretation[]`, `referenceRange[]` | keep low/high/text | `interpretation`, `ref_low`, `ref_high`, `ref_text` |
| `subject`, `encounter` | rewrite | `patient_key`, `encounter_id` |
| `performer[]`, `device`, `specimen`, `note`, `identifier` | drop | — |

Label by LOINC code list:
- `44261-6` PHQ-9, `70274-6` GAD-7, `55758-7` PHQ-2, `89204-2`/`93025-5` (behavioural screens) → `R` + `PSY`
- `72109-2` AUDIT-C, `82667-7` DAST-10, `72166-2` tobacco status → `R` + `ETH` (tobacco stays `N` + `ETH` tag)
- HIV tests (`75622-1`, `5017-9`, `56888-1`), viral load → `V` + `HIV`
- STI tests (chlamydia `21613-5`, gonorrhoea `21414-8`, syphilis `20507-0`) → `R` + `STD`
- pregnancy tests (`2106-3`, `19080-1`), contraception surveys → `N` + `SEX`
- genetic panels (rare in Synthea) → `R` + `GDIS`
- everything else → `N`

Datasets exposed: `labs` = `category ∈ {laboratory, vital-signs}`; surveys and social history are exposed only to `attending`/`consultant` and carry their labels.

### 2.5 `MedicationRequest` (+ `Medication` when referenced) → `medications`

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `status`, `intent` | keep | `status`, `intent` |
| `medicationCodeableConcept.coding` (RxNorm) or resolved `Medication.code` | keep | `code`, `code_system`, `display` |
| `authoredOn` | keep (quasi-identifier) | `authored_at` |
| `dosageInstruction[0].text`, `.timing.repeat.{frequency, period, periodUnit}`, `.doseAndRate[0].doseQuantity`, `.asNeededBoolean` | keep | `dosage_text`, `timing_frequency`, `timing_period`, `timing_period_unit`, `dose_value`, `dose_unit`, `as_needed` |
| `reasonReference[]` → `Condition` | rewrite to our `conditions.id` | `reason_condition_id` |
| `subject`, `encounter` | rewrite | `patient_key`, `encounter_id` |
| `requester`, `performer`, `dispenseRequest`, `insurance`, `identifier`, `note` | drop | — |

Label by RxNorm ingredient class list: antidepressants / antipsychotics / mood stabilisers → `R` + `PSY` (derived); antiretrovirals → `V` + `HIV`; opioid agonist therapy (buprenorphine, methadone, naltrexone) → `R` + `ETH`; controlled substances (opioids, benzodiazepines, stimulants) → `R`; hormonal contraception → `N` + `SEX`.

`MedicationAdministration` is not ingested for the demo; if needed later it becomes `medication_events`.

### 2.6 `AllergyIntolerance` → `allergies`

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `clinicalStatus`, `verificationStatus`, `type` (`allergy`/`intolerance`), `criticality` | keep | same names |
| `category[]` (`food`, `medication`, `environment`, `biologic`) | keep | `category` |
| `code.coding` (SNOMED / RxNorm / UNII) | keep | `code`, `display` |
| `reaction[0].manifestation[0].coding`, `reaction[0].severity` | keep | `reaction_code`, `reaction_display`, `severity` |
| `recordedDate`, `onsetDateTime` | keep | `recorded_date`, `onset_date` |
| `patient`, `encounter` | rewrite | `patient_key`, `encounter_id` |
| `recorder`, `asserter`, `note`, `identifier` | drop | — |

Label: `N`. The `dietary_staff` role (if adopted) sees `category = food` rows only.

### 2.7 `DocumentReference` (+ duplicate `DiagnosticReport` note) → `notes` and the vector store

Synthea emits each clinical note twice: as `DocumentReference.content.attachment.data` (base64 `text/plain`) and as `DiagnosticReport.presentedForm` with category `34117-2`. Ingest **only** `DocumentReference`; skip `DiagnosticReport` rows whose `category` is `34117-2`.

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `type.coding` (LOINC, e.g. `34117-2` History and physical) | keep | `type_code`, `type_display` |
| `category[0].coding.code` (`clinical-note`) | keep | `category` |
| `date`, `context.period.start` | keep (quasi-identifier) | `authored_at` |
| `content[0].attachment.data` (base64) | decode → **Presidio** (recognisers: PERSON, DATE_TIME, AGE, LOCATION, PHONE, EMAIL, ID) → validate → chunk → embed | `notes.sanitized_ref` (MinIO object), chunks in Qdrant |
| `subject`, `context.encounter[0]` | rewrite | `patient_key`, `encounter_id` |
| `author[]`, `custodian`, `authenticator`, `identifier`, `securityLabel` (Synthea does not set it) | drop | — |

Synthea note text begins with the patient's name, age, and birth date ("Patient is a 45 year-old non-hispanic white male…"). Presidio must remove name and exact DOB; age ≥ 90 becomes `90+`; race/ethnicity phrases are removed by a custom recogniser (word list).

Label: `max(label of conditions and observations in the same encounter)` plus a keyword detector for `PSY`/`ETH`/`HIV` terms; `internal = true` for psychiatric notes so the `self` view omits them. LLM-generated notes and the eight planted injection notes use the same path and are flagged `provenance = generated` / `provenance = adversarial` in the manifest.

### 2.8 `DiagnosticReport` (non-note) → `diagnostic_reports` (view `imaging_reports`)

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `status` | keep | `status` |
| `category[0].coding.code` (`LAB`, `RAD`, `CT`, `MR`, `US`…) | keep | `category` |
| `code.coding` (LOINC) | keep | `code`, `display` |
| `effectiveDateTime`, `issued` | keep | `effective_at`, `issued_at` |
| `result[]` → `Observation` | rewrite to our `observations.id` | `diagnostic_report_results (report_id, observation_id)` link rows |
| `conclusion`, `conclusionCode[]` | keep; through Presidio | `conclusion_text`, `conclusion_code` |
| `imagingStudy[]` | rewrite | `study_id` |
| `presentedForm` | drop for `LAB`; for `RAD`/`CT`/`MR`/`US` decode text → Presidio → MinIO `reports/` | `report_ref` |
| `performer`, `resultsInterpreter`, `identifier` | drop | — |

Rows with `category = LAB` become panel groupings (no `report_ref`, enforced by CHECK); rows with imaging categories are visible through the `imaging_reports` view, the text tier that `/tools/imaging` serves. A CHECK rejects `category = 34117-2`, so the duplicated note can never land here. Label: inherits from the referenced study's body site and findings code list (`V` + `HIV` if HIV-related, otherwise `N`).

### 2.9 `ImagingStudy` → `studies`

| Element | Action | Target |
|---|---|---|
| `id` | keep | `source_id` |
| `status`, `started` | keep | `status`, `study_at` |
| `modality[]` (DICOM `CT`, `MR`, `US`, `CR`, `DX`) | keep first | `modality` |
| `numberOfSeries`, `numberOfInstances` | keep | `series_count`, `instance_count` |
| `procedureCode[0].coding` | keep | `procedure_code`, `procedure_display` |
| `series[].bodySite.coding` | keep first | `body_site` |
| `series[].uid`, `instance[].uid`, `series[].instance[].sopClass` | drop (or map to Orthanc ids when pixels are loaded) | `orthanc_id` nullable |
| `subject`, `encounter` | rewrite | `patient_key`, `encounter_id` |
| `referrer`, `interpreter`, `endpoint`, `identifier` | drop | — |

Label: `N`; `dietary_staff`, `researcher`, `caregiver` never reach this dataset; `care_team` sees metadata only; `attending`/`consultant` see the report text via `/tools/imaging`. Pixels are never a tool output.

### 2.10 Optional: `Immunization`, `Procedure`

Ingest only if a track finishes early. `Immunization`: `vaccineCode` (CVX), `occurrenceDateTime`, `status`, `primarySource`. `Procedure`: `code` (SNOMED), `performedPeriod`, `status`, `reasonReference`. Both `N`, both plain datasets.

### 2.11 Optional: `NutritionOrder` → `diet_orders` (chef persona)

Synthea does not emit it; hand-seed. `status`, `intent`, `dateTime`, `oralDiet.type[].coding` (SNOMED diet codes), `oralDiet.texture`, `oralDiet.fluidConsistencyType`, `excludeFoodModifier[]` (as neutral codes `no-pork`, `no-shellfish`, not religion labels), `allergyIntolerance[]` → our `allergies.id`, `patient` → `patient_key`, `encounter`. Label `N`; note the irreducible inference (renal diet → kidney disease) on the threat-model page.

### 2.12 Not ingested (skipped and counted)

`Claim`, `ExplanationOfBenefit`, `Coverage`, `Organization`, `Practitioner`, `PractitionerRole`, `Location`, `Provenance`, `CarePlan`, `Goal`, `Device`, `SupplyDelivery`, `Media`, `MedicationAdministration`, `Basic`, `Group`.

---

## 3. Datasets, tools, and who sees what

| Dataset (tool parameter) | Tables | attending | care_team | consultant | caregiver | patient (self) | researcher | dietary_staff |
|---|---|---|---|---|---|---|---|---|
| `labs` | observations (lab, vitals) | full | `REDACT V` | specialty subset | scope tuple only | own, `REDACT internal` | aggregate only | — |
| `conditions` | conditions | full | `REDACT V` | full | scope tuple only | own | aggregate only | — |
| `meds` | medications | full | `REDACT V` | full | scope tuple | own | aggregate only | — |
| `encounters` | encounters | full | full | full | scope tuple (appointments) | own | aggregate only | — |
| `allergies` | allergies | full | full | full | full | own | aggregate only | `category = food`, own ward |
| `notes` (`/tools/notes`) | notes + Qdrant | full | `REDACT V` | full | `caregiver_notes` tuple | own, no `internal` | — | — |
| `imaging` (`/tools/imaging`) | imaging_reports, studies | report text | metadata | report text | — | own metadata | — | — |
| `imaging_pixels` / `document_bytes` (`POST /media/sign`, dashboard only) | Orthanc, MinIO `reports/` | signed URL | — (metadata only) | signed URL | — | own studies and own sanitized uploads | — | — |
| `diet` | diet_orders | full | full | — | scope tuple | own | — | own ward |
| `aggregate` | any of the above | own patients | — | — | — | — | `k_min`, `allowed_dims`, date shift | own ward counts |

`—` means the dataset is not in the role's allowlist: the PDP returns the uniform 404, and the tool never touches the table.

---

## 4. Emitted resources (exports only)

### 4.1 `AuditEvent` ← `audit_events`

| Our column | R4 element | R5 / R6 element |
|---|---|---|
| `event_type` | `type` (Coding) + `subtype` | `category` (R5) / `type` (R6) + `code` (R5) / `subtype` (R6) |
| `recorded_at` | `recorded` | `recorded` |
| `agent_user` | `agent[0].who` (Reference `Practitioner`/`Patient`/`RelatedPerson` by opaque id), `agent[0].requestor = true` | same, `who` is 1..1 |
| `agent_software` | `agent[1].who` (Reference `Device`), `agent[1].type = 110150 Application` | same |
| `purpose_of_use` | `purposeOfEvent` and `agent[0].purposeOfUse` | `authorization` and `agent[0].authorization` |
| `entity_patient` | `entity[0].what` (Reference `Patient/p_xxx`), `entity[0].role = 1 Patient` | same |
| `entity_resource` | `entity[1].what` | same |
| `entity_query` | `entity[1].query` (base64 of the tool parameters) | same |
| `outcome` | `outcome` code (`0` success, `4` minor failure, `8` serious) | `outcome.code` |
| `detail.reason_code`, `policy_id`, `policy_version` | `outcomeDesc` + `entity.detail[]` | `outcome.detail[]` + `entity.detail[]` |
| `prev_hash`, `row_hash` | extension `patient360-audit-chain` | same |

`GET /audit/{id}?format=fhir&fhirVersion=R4|R5`.

### 4.2 `Consent` ← OpenFGA tuple + `consent_granted` / `consent_revoked` audit rows

| Our data | R4 element | R5 / R6 element |
|---|---|---|
| tuple exists / revoked | `status = active` / `inactive` | same |
| `scope` | `scope = patient-privacy`, `category = 59284-0` | `category` |
| `patient_key` | `patient` | `subject` |
| `granted_by` (audit) | `performer[]` (Patient or Organization) | `grantor` / `grantee` |
| `recorded_at` | `dateTime` | `date` |
| our `policy_id@version` | `policyRule` (Coding) | `policyBasis.url = /policies/{id}@{version}` |
| — | `provision.type = permit` | `decision = permit` (required when provisions exist) |
| relation (`caregiver`, `consultant`…) | `provision.actor[].role`, `provision.actor[].reference` | same |
| `start`, `expiry` | `provision.period` | same |
| datasets in scope | `provision.class[]` (resource types) | same |
| purpose | `provision.purpose[]` (`TREAT`, `PATRQT`) | same |
| label ceiling | `provision.securityLabel[]` | same |

`GET /consents?patient=p_103&format=fhir`.

### 4.3 `OperationOutcome` ← uniform error bodies

- Not found (unauthorized **or** nonexistent, byte-identical): `issue[0].severity = error`, `code = not-found`, `diagnostics = "Resource not found"`. No patient key echoed.
- Deny with reason: `severity = error`, `code = security`, `details.coding = {system: patient360/reason-codes, code: off_duty_step_up_required}`, `extension audit-id`.
- Audit unavailable (fail closed): `code = transient`, HTTP 503.

### 4.4 `Provenance` ← patient-submitted uploads

`target = DocumentReference/{note_id}`, `agent[0].type = author`, `agent[0].who = Patient/p_xxx`, `recorded`, `activity = CREATE`. Drives the "patient-reported" provenance badge in the UI.

### 4.5 `Bundle`

`type = collection` wrapper for any multi-resource export.

---

## 5. Terminology to load

| Code system | Used for | Source |
|---|---|---|
| LOINC | observations, report codes, note types | subset shipped with Synthea; label list in `labels.yaml` |
| SNOMED CT | conditions, procedures, encounter types, body sites, diet types | subset; subsumption via a small closure table for mental-disorder and HIV hierarchies |
| RxNorm | medications | subset + ingredient class list |
| CVX | immunizations (optional) | subset |
| DICOM modality | studies | fixed list |
| HL7 v3 Confidentiality, ActCode, ActReason | labels, obligations, purpose of use | `hl7.terminology.r4#7.1.0` package |
| Consent scope/category, audit-event-type, object-role, participation-role-type | exports | FHIR core R4 value sets |

Load THO as a package. Do not hand-copy codes into Python.

---

## 6. Optional: SQL on FHIR v2 view definitions

If time allows, express the projections in §2 as `ViewDefinition` resources in `backend/ingestion/views/*.json` (`fhirVersion: ["4.0.1"]`, `resource`, `select[].column[]`, `where[]`), and have `synthea_flatten.py` execute them. Eight views: `patients`, `encounters`, `conditions`, `observations`, `medications`, `allergies`, `notes`, `studies`. This makes the flatten portable and lets the threat-model page say the projection is a declared HL7 view, not ad-hoc code.

---

## 7. Tests this plan implies

- **Allowlist leak test per resource**: project a Synthea bundle; assert no `name`, `address`, `telecom`, `identifier`, `extension`, `text`, `race`, `ethnicity`, `birthDate` (full), or `maidenName` string survives anywhere in the target JSONB or text columns.
- **Label assignment**: a fixture bundle with one condition per sensitivity code yields the expected `confidentiality`/`sensitivity[]`.
- **Reference resolution**: `urn:uuid:` and relative references both resolve; an unresolvable `subject` quarantines the resource and increments the manifest counter.
- **Idempotency**: re-running the batch changes zero rows.
- **Unknown resource types**: `Claim` in the bundle is skipped and counted, not fatal.
- **Note de-identification**: planted truth set (names, DOBs, ages ≥ 90, race phrases) is fully removed; the eight adversarial notes are present and flagged.
- **Duplicate note suppression**: `DiagnosticReport` with category `34117-2` produces no `notes` row.
- **Export round-trip**: one `AuditEvent` and one `Consent` export validate against the R4 core StructureDefinitions.

---

## 8. Open items

- Whether to ingest `Immunization` and `Procedure` (decide by Day 3 based on time).
- Chef persona: in the OpenFGA model (`ward#staff`, `patient#admitted_to`, `can_read_diet`; Build Plan §4.2, demo step 12). Still Track B: hand-seed one `NutritionOrder` for `p_101` with `ward = 'w_3b'` and a food allergy, the `identity.users` row for `u_lindqvist`, and the worker's `admitted_to` derivation from inpatient encounters.
- Exact SNOMED/LOINC/RxNorm code lists for `labels.yaml`; seed from the demo patients first, extend from the 100-patient batch by inspecting actual codes emitted.
