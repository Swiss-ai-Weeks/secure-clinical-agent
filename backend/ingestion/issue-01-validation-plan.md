# Ingestion 01: validation and next steps

Historical review recorded before worker implementation. The user subsequently supplied Synthea and authorized implementation; see [the current runbook](RUNBOOK.md) and [source-worker validation](source-worker-validation.md). Findings below describe the earlier review baseline rather than the current implementation state.

Reviewed 2026-09-17. Scope: [roadmap #2](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/2), especially [Ingestion 01 / issue #3](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/3). The user subsequently confirmed the handoff acceptance-scenario boundary and approved 10 smoke patients / 100 seed patients. Remaining scope and generator decisions stay open; pipeline implementation is outside this review.

## Repository baseline

- Current branch: `ingestion-pipeline`, HEAD `5aabb8c`.
- Refreshed `origin/main`: `50f0dd180a6666ff8712e8c8dcb1b9f68791083f`; no local `main` branch exists.
- Comparison: `git diff origin/main...HEAD`. One extra commit updates four Markdown files (28 additions, two removals): the execution backlog, links from the ingestion README and plan, and tracker clarification in the decision map.
- Main already contains backend deployment configuration, the ingestion plan, local decision tickets, and source/model research. Neither main nor this branch contains an ingestion worker or an ingestion test runner.
- GitHub issues #2–#12 are open. Issue #3 has no comments and its four acceptance checklist items are unchecked at review time.
- Pre-existing staged documentation moves and untracked product documents/assets are separate from the committed comparison and remain untouched.

## Standards review

No findings in the committed diff. Ingestion/deployment locations follow `backend/README.md`; the map distinguishes implementation status from unresolved design decisions. All 31 relative Markdown links in the changed documents resolve locally. No applicable code-smell findings in this documentation-only change.

## Spec review

No regressions or scope expansion in the committed diff. The following are unfinished issue requirements, not defects introduced by the latest commit:

| Issue #3 requirement | Evidence and remaining work |
| --- | --- |
| Approved count, note types/language, resource coverage, date window, clinical success examples | Counts approved during this review: 10 smoke / 100 seed. Note types/language, resource coverage, date window, and concrete clinical success examples remain open. |
| Supplied generator URL and inspected contract | Missing URL, request/response evidence, license review, local/hosted choice, reproducibility controls, failure behavior, and a synthetic example. Do not substitute an invented generator or API. |
| Existing research baseline; documentation versus runtime | [Research](research/source-model-contracts.md) exists and makes this distinction. Reference it in the final handoff; runtime model/profile, collection, schema, and de-identification checks remain future work. |
| Batch-first scope, optional adversarial fixtures, exclusions | Batch-first and exclusions are documented; confirm scope and explicitly include or exclude a separate synthetic adversarial evaluation set. |

Standards: zero findings. Spec: zero change regressions; three acceptance areas remain incomplete or require decisions. Missing generator evidence prevents adapter design.

## Plan before implementation

1. Preserve the now-approved 10 smoke / 100 seed counts. Obtain the generator project/API URL and remaining cohort decisions: note types, language, resource coverage, date window, clinical success examples, and adversarial fixture choice. Preserve unanswered items as unresolved.
2. Inspect the supplied generator's actual documentation/source. Record version, license, input/output formats, execution location, reproducibility limits, failure behavior, and a credential-free synthetic example. No live generation is needed to inspect the contract.
3. Record the agreed scope and evidence in the linked local decision tickets; keep the published research baseline and outstanding runtime checks explicit. Do not mark issue #3 complete until all its acceptance criteria have evidence.
4. Test boundary confirmed by the user: the issue #3 decision handoff consumed by the Synthea fixture and note-adapter work. This issue does not currently define a software API or require a new validator service.
5. Handoff acceptance scenarios are now written at that boundary in [tests/issue-01-handoff.feature](tests/issue-01-handoff.feature). They are manual scenarios, not executable adapter tests; no generator API has been invented.
6. Review the [current evidence assessment](tests/README.md) and stop before implementation. Fixture generation (#4), identity (#5), and the note adapter (#7) remain later work subject to their prerequisites.

## Acceptance scenario coverage

The confirmed boundary is covered by 13 scenario definitions (26 cases when the three outlines are expanded). They have no step runner and are not reported as passing automated tests.

- Scope completeness and traceable approval, including preserving the approved counts without implicitly approving other proposals.
- Generator contract evidence, including missing URL, missing synthetic example, and unsupported reproducibility claims.
- Separation of documentation findings from runtime verification.
- Explicit batch scope, excluded features, and the optional adversarial-fixture decision.
- A complete handoff with cited evidence, without implying that the pipeline ran or that generated data was published.

## Validation evidence

- `git diff --check origin/main...HEAD`: passed.
- Shell syntax checks for Qdrant and OpenFGA initialization scripts: passed.
- `docker compose --env-file backend/deploy/patient360/.env.example -f backend/deploy/patient360/compose.yaml config --quiet`: passed; static configuration only.
- Frontend `npm test`: after `npm ci --no-audit --no-fund` installed the locked dependencies, all 12 unit tests in six files passed, followed by TypeScript checking and the production build. The initial missing-dependency failure (`vitest: not found`) is resolved. Browser end-to-end tests were not run.
- Local changes: `git diff --check` passed; all 41 local Markdown links in the new and updated review documents resolve.
- New handoff tests: 13 manual scenario definitions / 26 expanded cases written; no executable steps added. The evidence assessment leaves complete-handoff readiness blocked on missing inputs.
- No ingestion runtime validation is possible against this checkout's absent worker. No services were started and no datasets were generated by this review.
