# Unpublished chunk and embedding validation

Verified on 2026-09-18 against the current working checkout. This implements the next worker stage under the [accepted embedding contract](../../.scratch/ingestion-pipeline/issues/09-vector-contract.md#answer). It does not establish seed ingestion, publication or authorized retrieval acceptance.

## Implemented behavior

[note_vectors.py](note_vectors.py) loads the pinned local tokenizer with `tokenizers==0.22.2`, checks its SHA-256 and refuses a missing or incompatible tokenizer. It splits sanitized notes at Markdown section headings, prefers paragraph/sentence boundaries within long sections, and enforces 512 content tokens including repeated sanitized heading context. Body overlap is at most 64 tokens. Heading and body retain separate half-open Unicode code-point offsets into the exact sanitized note.

The worker sends original heading/body input in sequential passage batches of eight with `truncate: NONE`. It independently counts the full server-formatted input, including special tokens. Every response must match model, count, complete unique indices, 2,048-dimensional finite nonzero vectors and expected token usage. Response order is reconstructed by index. All inputs are checked before the first request; an invalid response fails the note without saving partial vectors.

[notes.py](notes.py) runs the existing sanitizer/canaries first, then produces `chunked` and optionally `embedded` artifacts. Embedding rechecks preparation identity, tokenizer, policy and exact chunks. Files are atomically saved with owner-only permissions. Clinical/evaluation artifacts use separate directories and remain unpublished. Preparation identities are deliberately distinct from the final versioned store identities still to implement. The former publication shortcut now fails before store calls.

## Verification results

The final ingestion test run discovered **74 tests: 68 passed and six live PostgreSQL tests were skipped**. The passing tests include the live embedding check. PostgreSQL checks were not opted into because this change adds no SQL writes or schema changes.

```bash
PYTHONPATH=/tmp/p360-tokenizer-probe-20260918/packages \
RUN_EMBEDDING_LIVE_TESTS=1 \
PATIENT360_EMBED_TOKENIZER=/home/nvidia/.cache/nim/embed/weights/embed/tokenizer.json \
python3 -m unittest discover -s backend/ingestion/tests -p 'test_*.py' -v
```

The live check sent only a harmless Markdown library-hours section through the actual model tokenizer and `http://127.0.0.1:8001/v1/embeddings`. It produced multiple valid chunks/vectors with exact citations and matching local/server token usage. No clinical source notes were sent by this check, and it made no Qdrant, PostgreSQL or grant writes.

Offline coverage includes Unicode and whitespace fidelity, source coverage, overlap/progress, heading-only sections, oversized headings, deterministic preparation identities, canary removal before inference, changed-artifact rejection, no tokenizer fallback, reordered/malformed model responses, and command-line behavior. A simulated second-batch failure verifies that the chunked artifact survives while no partial embedded artifact is created. Ruff checks passed for the changed worker and test files using the backend's lint configuration.

## Remaining work

The full sanitizer policy, immutable embedding contract and cached-rendition manifests, opaque source linkage, versioned Qdrant collections/UUID points/indexes, trusted eligibility ledger and authorized query boundary remain to implement or validate. Local metadata and `published=false` are not a cross-store gate. The separate application upload helper was not migrated by this step. Recorded Compose drift also remains in [embedding readiness](embedding-readiness.md#concurrent-deployment-drift-observed).

Next implement versioned vector staging and trusted eligibility, then prove the approved three-note pilot before smoke and seed. Follow the [runbook](RUNBOOK.md#unpublished-note-preparation-and-embedding) for dependency setup and the completed stage's commands.
