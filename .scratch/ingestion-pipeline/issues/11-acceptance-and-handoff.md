# Define acceptance evidence and the implementation handoff

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: Codex
Blocked by: 10

## Question

What checks and measured results prove the selected design is ready to implement and subsequently prove that its first seed succeeded?

Specify a tiny reproducible fixture and the agreed full seed, expected patient/resource/note/chunk counts, consistent linkage, FHIR code/unit/date preservation, explicit excluded/quarantined counts, and clinical consistency checks. Require identifier-canary checks at embedding inputs, persisted payloads/JSON, and logs; allow/deny/revocation checks before reranking or generation; repeat-run idempotency; interruption/restart recovery; grant reseeding/persistence; and incompatible-dimension rejection.

Define basic retrieval relevance examples over synthetic ground truth and a later reranker comparison boundary without adding a reranker now. Confirm an ordered implementation backlog and acceptance commands after preceding decisions close. Planning completion means an approved implementable spec with no remaining prerequisite decisions; it does not claim the databases are populated or the pipeline is running.

## Comments

### Approved demonstration input — 2026-09-17

[Choose the first cohort and ingestion success criteria](03-cohort-and-success.md#answer) is resolved. Use its approved [clinical demonstration examples](../../../backend/ingestion/clinical-demo-examples.md) and access expectations as inputs to the eventual executable acceptance checks. The examples distinguish note narrative from structured measurements and historical from current conditions. Exact ranking thresholds, sanitized fixture mappings, and runtime commands remain to be specified here after the blocking contracts resolve; the source-evidence checks are not retrieval tests.

### Approved attack cases — 2026-09-18

The [note-generation/evaluation resolution](06-note-generation-contract.md#answer) fixes eight cases and unchanged controls, with expected authority, patient-access, export and answer/citation outcomes. [Fixture validation](../../../backend/ingestion/evaluation-validation.md) verifies local lineage/reproducibility and unchanged clinical stores. All end-to-end cases remain `not_run`; require the real sanitizer, authorization and retrieval/generation path before recording resistance or access outcomes.

### Acceptance discussion resumed — 2026-09-18

Claimed the first open, unblocked ticket after reading the current tracker. The checkout is now `main` at `b49332b` with concurrent application/frontend/ingestion changes present. The current handoff and map index lag behind the resolved child tickets; their completion claims are not fresh runtime evidence.

The live embedding readiness and model endpoints again returned HTTP 200. Earlier harmless passage/query and oversize probes are recorded in [embedding readiness evidence](../../../backend/ingestion/embedding-readiness.md); those establish service behavior, not end-to-end note ingestion or retrieval acceptance.

**Pending baseline question:** the current resolved chunking ticket describes provisional whitespace-counted 384/48 chunks and the vector ticket names fixed initial collections. In the preceding user discussion, the accepted strategy was section-aware, model-tokenizer-counted 512/64 chunks and physical collections tied to the embedding contract, with staged document versions. The user has been asked whether acceptance should retain that earlier approved strategy (recommended) or first review the newer strategy. No superseding choice is assumed and no existing resolution is rewritten by this comment.

After settling that baseline, define executable evidence for tokenizer limits and preservation, source-grounded retrieval, authorization/revocation, replay and interrupted publication. Keep implementation existence, local unit checks and live cross-store acceptance distinct. This ticket remains claimed; no acceptance resolution or full-pipeline success is recorded.

### Baseline answer — 2026-09-18

The user answered “q1 yes lets do that”, accepting the recommendation to retain the earlier approved strategy. The canonical amendments are recorded in [Choose note de-identification and chunk boundaries](07-deid-and-chunking.md#user-confirmed-chunking-amendment--2026-09-18) and [Choose the embedding and Qdrant note-chunk contract](09-vector-contract.md#user-confirmed-collectionversioning-amendment--2026-09-18). Current shortcuts are implementation gaps, not replacements for those decisions.

### Pilot and retrieval acceptance — approved 2026-09-18

- **First end-to-end proof:** pilot using the three approved clinical demonstration notes, with real sanitization, tokenizer-aware chunks, passage vectors, isolated contract-specific test storage, publication eligibility, authenticated query retrieval and exact citations. Prove allowed, denied and revoked access before scaling to the already approved 10-patient smoke and 100-patient seed. The pilot supplements those cohorts; it does not replace them. Publication still requires all prerequisite checks to pass.
- **Retrieval usefulness:** initial gate of relevant note evidence among the top five authorized chunks for each of the three fixed demonstration queries, using source-checked expected passages and document lineage. If the answer requires two passages, both must be present. Score thresholds and a particular top-one result are not required. Structured measurements retain separate Observation evidence/citations, and historical pneumonia stays historical. This small fixture gate is not a general retrieval-quality claim.

The user answered “yes I accept both”, approving these two recommendations. These are acceptance targets, not measured results. The ticket remains claimed while the remaining acceptance behavior is discussed.

### Failure and replay evidence required by the retained contracts

The following checks turn existing requirements into evidence; they do not introduce a different publication or access policy:

- Reject an oversized input with truncation disabled; no partial vector or published note is admitted. Verify exact tokenizer boundaries and model-required overhead separately from the earlier observed 4,096-token error.
- Interrupt an isolated test run between sanitized-artifact, SQL, vector and publication steps. The incomplete document version remains unreadable; retry completes without duplicate active chunks or skipped content.
- Replay identical inputs/settings and compare document identities, point IDs, content hashes and counts. Test a changed/shorter document revision separately: only its eligible version is returned, with no obsolete trailing chunks. Stricter labels withhold the earlier version immediately.
- Deny missing/invalid access metadata, incompatible model/collection contracts and unavailable authorization dependencies before exposing text. Verify revocation after successful retrieval and across grant-store restart/replay; retries must not renew or restore grants.
- Plant synthetic identifier canaries and verify their absence at actual embedding inputs, accepted stored payloads and ordinary logs. A quarantined note never reaches embedding or retrieval. Keep adversarial fixtures in their isolated corpus.
- Record passed, failed and not-run checks distinctly, with model/policy identities, input and output counts, exclusions/quarantines and safe evidence links. Passing local mock tests does not substitute for these live checks.

### Partial-batch acceptance — approved 2026-09-18

The user accepted the recommendation. The resulting publication policy is recorded in [Choose batch orchestration, publication, and recovery](10-batch-lifecycle.md#user-approved-partial-batch-policy--2026-09-18). For acceptance, fail the baseline seed check when an approved baseline note is unexpectedly quarantined. Intentional rejection fixtures have their own expected outcomes and do not reduce the required three-example retrieval coverage. Operational progress is distinct from a claim that the complete seed passed.

## Answer

Resolved 2026-09-18 after the user accepted the strategy baseline, pilot scope, retrieval gate and partial-batch recommendation in the live exchange. This resolves acceptance policy and the handoff sequence; it does not record a passed end-to-end run or completion of the map.

### Acceptance scope and evidence

- Follow the approved pilot and retrieval criteria above: three source-grounded clinical examples first, then the approved 10-patient smoke and 100-patient seed. Relevant passages must appear among the top five authorized chunks for each fixed query; keep structured measurements and note citations separate. Preserve negation, event dates, units, patient/encounter linkage and the historical/resolved status of pneumonia.
- The source baselines are 500 notes for the smoke cohort and 4,645 notes for the seed. The earlier committed full structured seed contains 100 patients, 4,645 encounters, 3,579 conditions and 70,843 Observation rows including components. These are recorded baselines, not newly reverified counts. Report input, prepared, quarantined, excluded and eligible note counts without double counting; unexpected losses fail acceptance.
- Derive exact chunk counts from the pinned tokenizer/chunking policy and prepared fixture manifests. Do not guess counts from words or require one chunk per note. Freeze the expected fixture identities, content hashes and counts before store/replay checks, then reconcile them with the actual eligible vectors and citations.
- Pass the failure/replay checks specified above using isolated real stores and the actual embedding and authorization boundaries. Validate required metadata and model/collection compatibility before any text exposure or vector admission. A collection payload flag alone does not establish publication or authorization.
- Expected quarantine/rejection test cases pass only when they remain unembedded and unreadable. Unexpected quarantines fail baseline-seed acceptance even if individually eligible notes have published. Report partial runs explicitly.
- Retain the eight approved adversarial variants and three unchanged controls in isolated evaluation storage. Full security acceptance requires the real sanitizer, retrieval/authorization and generation path with their approved outcomes; fixture generation or the three-note pilot alone cannot mark those tests passed. Do not add a reranker to this milestone.
- Each evidence report identifies the input manifest, model/weights/tokenizer and policy versions, fixture identities, stage counts, replay/recovery results and passed/failed/not-run checks. Keep raw identifiers and credentials out of ordinary reports; link restricted diagnostic evidence by opaque references.

### Implementation handoff

The [ordered implementation backlog](../../../backend/ingestion/issues.md) remains the execution index. Apply this concrete order to its remaining stages:

1. Finish the [embedding and Qdrant contract](09-vector-contract.md): measure tokenizer input boundaries/overhead and operational batch behavior, then finalize contract identity and compatible versioned payload/index/point-ID rules. The earlier basic model probes remain useful evidence, not a substitute for these checks.
2. Reconcile whole-note sanitization/admission with the approved policies, implement section-aware tokenizer-based chunks and exact offsets, and wire passage embedding with response validation into the note worker.
3. Implement trusted metadata, publication eligibility, authorization checks and replay/version replacement so the pilot can use the real path. Preserve source artifacts, the identity registry and existing stores.
4. Run the isolated pilot with the fixed queries and access changes, then smoke, then full seed. Run interruption, replacement, quarantine and adversarial cases in separate fixtures and record every unmet gate.
5. Publish the measured acceptance report and exact reproducible commands in the runbook. Existing unit/prepare-only commands must not be described as full live acceptance commands.

Proposed future acceptance interface (specification only; no such executable exists yet): `python3 backend/ingestion/acceptance.py --stage pilot|smoke|seed --output <restricted-report-directory>`. Implement stages as explicit choices and return nonzero for failed or required not-run checks. The report distinguishes expected negative-test outcomes from unexpected baseline rejection. This is an implementation convention, not evidence of a command having run.

Runtime tests were not run in this decision-only update. Exact contract measurements remain open in their owning ticket; reopening that ticket does not undo the accepted strategy or require the user to reapprove it.
