# Define grants, chunk ACL metadata, and retrieval enforcement

Parent: [Plan the Patient360 synthetic ingestion pipeline](../map.md)
Type: grilling
Label: wayfinder:grilling
Status: resolved
Assignee: none
Blocked by: 03, 04

## Question

What access policy should the seed grants and each vector chunk express, and how will retrieval enforce it before any text reaches a reranker or language model?

Current OpenFGA model defines viewer = care_team OR consented. Decide whether this represents intended consent semantics; do not silently change it to AND or assume it handles expiry, denial, tenancy, or break-glass. Specify required patient/tenant/security metadata, provenance of grants, and fail-closed handling for missing metadata. Avoid expanding changing user membership into stale per-chunk user lists without an invalidation strategy.

Define model upload, store/model ID discovery, deterministic tuple seeding, persistence or safe reseeding (OpenFGA currently uses memory), and grant revocation/expiry checks. Decide how trusted server-side policy becomes Qdrant filters and how PostgreSQL reads use the same policy. Filters and tags do not by themselves form an authorization boundary; clients/agents must not bypass it through direct store access. Include allowed, denied, missing-metadata, revoked, and cross-patient cases.

## Answer

Locked 2026-09-18. OpenFGA remains the only grant store. Demo tuples stay in `tuples.demo.yaml` via `openfga-init`. `backend/ingestion/seed_grants.py` is authoritative for time-relative windows, `consent_granted` rows with `detail.seeded=true`, Synthea-key mappings for the three approved clinical demos (`u_chen` attending), and worker-owned placements. No bulk care grants on the other ~97 patients.

Retrieval never trusts Qdrant tags as the boundary. `POST /tools/notes` calls PDP `evaluate` on `Resource(type="notes")` first, then a **server-built** Qdrant filter (`patient_key`, `published=true`, allowed `confidentiality`, `internal=false` for self). Caller filters may only narrow. Missing ACL metadata rejects the batch. Revocation is the next OpenFGA check (cache off). Cross-patient questions are the uniform 404.
