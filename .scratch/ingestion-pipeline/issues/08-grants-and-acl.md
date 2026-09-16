# Define grants, chunk ACL metadata, and retrieval enforcement

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: open
Assignee: none
Blocked by: 03, 04

## Question

What access policy should the seed grants and each vector chunk express, and how will retrieval enforce it before any text reaches a reranker or language model?

Current OpenFGA model defines viewer = care_team OR consented. Decide whether this represents intended consent semantics; do not silently change it to AND or assume it handles expiry, denial, tenancy, or break-glass. Specify required patient/tenant/security metadata, provenance of grants, and fail-closed handling for missing metadata. Avoid expanding changing user membership into stale per-chunk user lists without an invalidation strategy.

Define model upload, store/model ID discovery, deterministic tuple seeding, persistence or safe reseeding (OpenFGA currently uses memory), and grant revocation/expiry checks. Decide how trusted server-side policy becomes Qdrant filters and how PostgreSQL reads use the same policy. Filters and tags do not by themselves form an authorization boundary; clients/agents must not bypass it through direct store access. Include allowed, denied, missing-metadata, revoked, and cross-patient cases.
