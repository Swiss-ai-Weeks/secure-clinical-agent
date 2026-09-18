# Move source resource identifiers into restricted provenance

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: none
Blocked by: 05

## Question

How should the temporary raw non-patient `ResourceType/id` values in clinical `source_id` columns move into restricted provenance while preserving replay, source traceability, patient/encounter joins, citations, and grants?

The user explicitly accepted these raw resource IDs temporarily when adopting main's schema, with this follow-up required. Raw patient identities still belong in restricted linkage, and application/embedding outputs still use opaque identities and citations. The temporary clinical upsert keys have no source namespace column; the first importer must stay within the agreed namespace.

Specify the namespace-aware opaque replacement keys, restricted mapping permissions/storage, backfill and validation strategy, recovery behavior, and removal of raw IDs from clinical fields. Define evidence that replay stays idempotent, cross-namespace IDs cannot collide, references and citations remain stable, and unauthorized readers cannot access source mappings. Completing the initial importer does not automatically complete this follow-up.

## Answer

Locked 2026-09-18 as the stretch follow-up. Clinical `source_id` values stay namespaced `ResourceType/{opaque}` written only by the worker. Public citations remain `cite_id`. Raw Synthea resource ids belong in the restricted registry (`resource_links`), not in embeddings, Qdrant payloads, or `/tools/*` responses. Backfill: for each clinical row, replace `source_id` with `uuid5(identity_namespace, source_id)` and store the mapping in `registry.resource_links`. Replay stays idempotent because the mapping is durable. Unauthorized readers never get the mapping. This ticket is not a demo blocker; notes publication does not wait on it.
