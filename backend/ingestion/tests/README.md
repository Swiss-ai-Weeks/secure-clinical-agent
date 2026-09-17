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

The negative scenarios describe how a reviewer must handle incomplete or unsafe evidence. They do not require starting services or generating data. The complete-handoff scenario remains blocked until the remaining scope decisions arrive. The generator contract is now inspected and the source worker is implemented and tested.

## Current assessment, 2026-09-17

| Acceptance area | Evidence / result |
| --- | --- |
| Patient counts | Approved in this conversation: 10 smoke, 100 seed. Recorded in the local scope decision. No generated counts claimed. |
| Remaining cohort scope | Blocked: note types/language, resource coverage approval, date window, and clinical success examples are missing. |
| Generator contract | Supplied Synthea URL inspected; release/CLI/note-export contract documented, with restricted real synthetic examples generated and verified. |
| Research versus runtime | Existing research explicitly separates documentation findings from unverified runtime checks. Static configuration validation supplies no ingestion runtime evidence. |
| Milestone boundaries | Batch-first and exclusions are documented. Adversarial evaluation choice remains open. |
| Complete handoff | **Not fully ready.** The source worker is implemented under explicit demo defaults. Remaining clinical scope and downstream privacy/access decisions prevent claiming a complete ingestion pipeline; GitHub issue #3 remains open. |

This is an evidence assessment of the current handoff, not an automated scenario execution report. See [the validation plan](../issue-01-validation-plan.md) for the reviewed Git revisions and separate repository checks.
