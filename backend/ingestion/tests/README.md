# Ingestion verification

## Executable source-worker tests

Run from the repository root:

```bash
python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
```

[test_worker.py](test_worker.py) contains 18 passing public CLI tests. The tests replace Docker at the external process boundary and exercise real config validation, extraction, lineage checks, manifests, hashes, failure isolation, locking, replay, and artifact verification. They do not simulate a successful embedding or database stage. Real Synthea evidence is recorded in [source-worker-validation.md](../source-worker-validation.md).

## Manual handoff acceptance scenarios

[issue-01-handoff.feature](issue-01-handoff.feature) tests the documented seed-scope and generator-contract handoff in [GitHub issue #3](https://github.com/Swiss-ai-Weeks/secure-clinical-agent/issues/3). The user confirmed this boundary and approved **10 smoke patients / 100 seed patients** on 2026-09-17.

These are **manual acceptance scenarios**, written in Gherkin. They have no step implementation and must not be reported as passing automated tests. They are distinct from the executable source-worker tests above.

## How to review

For each scenario, inspect the [scope decision](../../../.scratch/ingestion-pipeline/issues/03-cohort-and-success.md), [generator decision](../../../.scratch/ingestion-pipeline/issues/01-note-generator-input.md), [plan](../plan.md), and cited generator evidence. For outlines, inspect each example separately. Record the evidence and outcome; distinguish a missing input from a failed implemented behavior. Never paste credentials or real patient records to exercise a negative scenario.

The negative scenarios describe how a reviewer must handle incomplete or unsafe evidence. They do not require starting services or generating data. The cohort decision is now resolved, including the clinical examples and access demonstration; the generator contract is inspected and the source worker is implemented and tested. The identity/provenance decision is also resolved, with its implementation pending. Detailed projection, sanitization, and access contracts remain separate prerequisites.

## Current assessment, 2026-09-17

| Acceptance area | Evidence / result |
| --- | --- |
| Patient counts | Approved targets: 10 smoke, 100 seed. Source validation records actual generated counts separately; this session reverified the seed at 100 patients and 4,645 notes. |
| Cohort scope | **Resolved.** Defaults, note types/language, resource coverage, date window, batch-first development-demo scope, and three clinical demonstrations with access checks are approved; see the [scope resolution](../../../.scratch/ingestion-pipeline/issues/03-cohort-and-success.md#answer) and [example evidence](../clinical-demo-examples.md). |
| Generator contract | Supplied Synthea URL inspected; release/CLI/note-export contract documented, with restricted real synthetic examples generated and verified. |
| Research versus runtime | Existing research explicitly separates documentation findings from unverified runtime checks. Static configuration validation supplies no ingestion runtime evidence. |
| Milestone boundaries | Batch-first development-demo scope and a small, separately labelled synthetic prompt-injection corpus approved. The evaluation corpus remains unimplemented and separate from the clinical seed. |
| Cohort and generator handoff | Cohort approval and the inspected generator contract are recorded for dependent work. No GitHub implementation-issue status was changed; the manual scenarios are not an automated test run. |
| Identity and provenance | [Decision amended](../../../.scratch/ingestion-pipeline/issues/04-identity-and-provenance.md#answer): birth year only, opaque patient keys, temporary internal raw resource source IDs, and restricted-provenance follow-up. Ingestion adapter/registry remain unimplemented. |
| Database bootstrap | User-authorized PostgreSQL volume replacement completed after backup. [Runtime evidence](../schema-integration.md) records isolated preflight, successful backup restore, live role/constraint checks, and healthy initialization. This is not ingestion/search acceptance. |
| Complete ingestion pipeline | **Not ready.** Downstream identity, privacy, access, storage, publication, and retrieval work remains. Approved examples are acceptance targets, not demonstrated search results. |

This is an evidence assessment of the current handoff, not an automated scenario execution report. See [the validation plan](../issue-01-validation-plan.md) for the reviewed Git revisions and separate repository checks.
