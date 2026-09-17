# Synthea generator contract

Inspected 2026-09-17 against upstream source. This is source-level research, not evidence of a successful local generation run. The recommended source is the official stable release below; `master-branch-latest` is a moving release and is unsuitable as a reproducibility pin.

## Release and artifact

| Property | Inspected value |
| --- | --- |
| Stable release | `v4.0.0`, published 2026-03-05 |
| Source commit | `0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813` |
| Official artifact | `synthea-with-dependencies.jar` |
| SHA-256 published by GitHub | `ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1` |
| Artifact size | 201,164,144 bytes |
| Java requirement | JDK 17 or newer; use a fixed runtime image/version for repeat comparisons |

Sources: [release](https://github.com/synthetichealth/synthea/releases/tag/v4.0.0), [release API with asset digest](https://api.github.com/repos/synthetichealth/synthea/releases/tags/v4.0.0), [download](https://github.com/synthetichealth/synthea/releases/download/v4.0.0/synthea-with-dependencies.jar), [pinned README](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/README.md).

Recommendation: download and verify this artifact during the worker build, record its digest in the run manifest, and fail on mismatch. A source build is possible with the pinned Gradle wrapper and `./gradlew shadowJar`; its manifest includes build time, JDK, and operating system, so a locally rebuilt JAR should not be expected to match the official artifact hash. [Build definition](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/build.gradle#L231-L250)

## CLI and reproducible inputs

`-s` sets the population seed; `-cs` independently sets clinician randomness. `-r YYYYMMDD` controls the reference time used for age/birthdate sampling; `-e YYYYMMDD` independently sets simulation end time. Both dates are parsed in UTC. Omitting either date or either seed leaves a wall-clock-derived default. The README's help excerpt omits `-e`, but the executable's argument parser supports it. [Argument parser](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/App.java#L79-L111), [generator defaults](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/engine/Generator.java#L145-L170)

`-p 10` or `-p 100` selects the approved smoke or seed population. Set `-o false` for an exact requested count: the default overflow behavior can export deceased patients and generate replacements, exceeding `-p`. This does not mean every exported patient is alive. Validate the resulting count rather than trusting process exit status. [Population loop](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/engine/Generator.java#L436-L450), [selection criteria](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/engine/Generator.java#L630-L696)

Recommended explicit export configuration:

```properties
generate.thread_pool_size=1
exporter.fhir.export=true
exporter.fhir.use_us_core_ig=true
exporter.fhir.us_core_version=6.1.0
exporter.fhir.transaction_bundle=false
exporter.fhir.bulk_data=false
exporter.hospital.fhir.export=false
exporter.practitioner.fhir.export=false
exporter.use_uuid_filenames=true
exporter.subfolders_by_id_substring=false
exporter.split_records=false
exporter.metadata.export=false
exporter.clinical_note.export=false
exporter.text.export=false
```

Set `exporter.baseDirectory` to a fresh restricted staging directory. Specify `exporter.years_of_history` deliberately: upstream defaults to 10, while 0 disables history filtering. The export history window is distinct from the birth-to-end simulation. Set JVM timezone and locale (`-Duser.timezone=UTC -Duser.language=en -Duser.country=US`) and pin the runtime as additional reproducibility controls. These are recommendations; the cohort's date window and geographic choice are product decisions. [Properties](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/resources/synthea.properties)

## FHIR and note contract

The FHIR exporter emits R4 patient Bundles. With transaction mode disabled they are `collection` bundles and provider/practitioner resources are embedded; transaction mode uses separate provider search references. Non-bulk resource `fullUrl` values and patient/encounter references use `urn:uuid:<id>`. UUID filenames and unsplit exports allow a stable `<patient-id>.json` file per patient. [Bundle construction and encounters](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/FhirR4.java#L406-L414), [embedded provider references](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/FhirR4.java#L936-L1001), [filename function](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/Exporter.java#L899-L908), [URL prefix](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/FhirR4.java#L3491-L3497)

**A separate note-generation API is not required for the initial Synthea adapter.** When US Core export is enabled, the R4 exporter generates an English template-based clinical note per exported encounter. Each note appears twice: as `DiagnosticReport.presentedForm` and as `DocumentReference.content[].attachment`. The attachment is base64-encoded UTF-8 with content type `text/plain; charset=utf-8`. Extract the DocumentReference copy once; preserve its ID, `subject.reference`, `context.encounter[].reference`, and date. Resolve these references against the actual Bundle entries and verify that the encounter belongs to the same patient. The upstream note types are History and Physical / Evaluation and Plan, not arbitrary discharge-summary or referral types. [Clinical-note construction](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/FhirR4.java#L2590-L2680)

The note-generation condition checks whether **DiagnosticReport** is allowed. Configuring an allowlist containing DocumentReference but excluding DiagnosticReport suppresses these notes. Do not filter only to `status=current`: upstream marks all but the last encounter's note `superseded`; that is not a reason to discard historical encounter evidence. [Generation condition](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/FhirR4.java#L501-L505), [note status](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/FhirR4.java#L2651-L2656)

`exporter.clinical_note.export=true` instead/additionally writes consolidated patient notes under `notes/`, newest encounter first. `exporter.text.export` is a different summary exporter. The consolidated notes do not supply the per-note patient/encounter linkage available in FHIR. The FreeMarker template contains date, chief complaint, history, allergies, medications, assessment and plan, including synthetic names; these are restricted source text, not already de-identified indexing payloads. [Flat-note export](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/Exporter.java#L430-L435), [consolidation](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/ClinicalNoteExporter.java#L45-L60), [English template](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/resources/templates/notes/note.ftl)

## Repeatability limits and acceptance evidence

Note resource IDs use the patient seed and encounter identity via upstream's deterministic `buildUUID` helper. Seeded population generation supplies a deterministic per-person seed sequence. However, source inspection alone does not prove bitwise-identical runs across operating systems, Java versions, or changed exporter flags. Keep the full configuration fixed and compare two fresh smoke runs before claiming that property. [ID helper](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/ExportHelper.java#L307-L342)

Upstream's metadata export definitely varies: it includes a random generator run ID, actual start time, runtime, and a wall-clock filename. Disable it for a repeatable artifact set or exclude it explicitly from content equality and record separate audit metadata. A build timestamp also varies in locally built JARs. [Metadata exporter](https://github.com/synthetichealth/synthea/blob/0185c09ea9d10a822c6f5f3ef9bdcbcbe960c813/src/main/java/org/mitre/synthea/export/MetadataExporter.java#L34-L124)

The first worker acceptance evidence should include exact distinct-patient count, Bundle shape, resolvable note/patient/encounter linkage, strict attachment decoding, nonempty notes, source hashes, stable ordering, and equal source/note hashes across two clean runs. These checks validate the adapter contract; full FHIR conformance, clinical acceptance, de-identification, model token limits, vector compatibility, authorization, and publication remain separate downstream checks.
