# Embedding service readiness

Verified locally on 2026-09-18. This records service startup and harmless inference probes, not completion of sanitization, the vector contract, vector ingestion, or authorized retrieval.

The subsequent [worker implementation and validation](vector-preparation-validation.md) adds tokenizer-aware section chunks and validated passage embeddings in unpublished local artifacts. Its harmless live test passed; store publication and the clinical pilot remain pending.

## Deployment

- Service: `embed` in [Patient360 Compose](../deploy/patient360/compose.yaml), container `patient360-embed`, GPU 0, endpoint `http://127.0.0.1:8001`.
- Served model: `nvidia/llama-nemotron-embed-vl-1b-v2`.
- Runtime: NIM 2.3.0, API 1.0.0, Rust backend. Runtime metadata reports `selectedModelProfileId: N/A`; do not invent a profile identifier.
- Image pinned to `sha256:93a3f17fa7d0b5ef1d31765a1eab4662669483bf85f2101a2c460aedd9b45480`.
- Persistent host weights: `~/.cache/nim/embed/weights`, mounted at `/model`; actual model files are under `weights/embed`.
- Persistent host compilation cache: `~/.cache/nim/embed/cache`, mounted at `/opt/cache`.
- Explicit download provider: `NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc`. This variable and both mount paths were checked against the cached image and [NVIDIA's NIM 2.3 instructions](https://docs.nvidia.com/nim/nemo-retriever/embedding/2.3/getting-started.html).
- Docker readiness invokes `/usr/bin/curl` directly. The image lacks `/bin/sh`, so the former `CMD-SHELL` health check failed even when the HTTP service was ready.

## Credential and recovery behavior

The ignored deployment `.env` had a blank `NGC_API_KEY`. An existing NVIDIA registry login in the local Docker credential configuration successfully authorized a download-only run. Its value was passed through the subprocess environment, never printed or copied into repository files. Model assets occupy about 3.2 GiB.

After downloading, the service was recreated using the ordinary Compose command with no download credential. Readiness and a query embedding passed with the saved weights; the recreated container had no nonblank `NGC_API_KEY`. The existing credential configuration remains unchanged. If weights are lost or replaced, supply an appropriate download credential again. A cached image alone does not contain these weights.

From the repository root, with these weights still present:

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml \
  up -d --no-deps --pull never embed
curl -fsS http://127.0.0.1:8001/v1/health/ready
curl -fsS http://127.0.0.1:8001/v1/models
```

Only the embedding service was recreated. Existing clinical stores and source artifacts were not changed.

## Measured checks

Requests used the exact served model ID, `encoding_format: float`, and `truncate: NONE`.

| Check | Observed result |
| --- | --- |
| Readiness | HTTP 200 with `ready: true` |
| Passage batch | Two harmless passages returned two vectors with unique indices `0, 1` |
| Query mode | One harmless question returned one vector with index `0` |
| Vector validity | Every tested vector had 2,048 finite values and nonzero norm |
| Norms | Approximately 1.000014 and 0.999995 for passages; 1.000011 for query |
| Very long input | 100,000-character request rejected with HTTP 400 and a reported 65,536-character maximum |
| Token oversize | 60,000-character request rejected with HTTP 422: input length 12,005 exceeds model maximum 4,096 |
| Cached recreation | Readiness and a 2,048-dimensional query vector passed after recreation without a download credential |

Passages were `The library opens at nine in the morning.` and `The garden contains red flowers.`; the query was `When does the library open?`. Oversize probes repeated `word ` 20,000 and 12,000 times. No raw or sanitized seed notes were sent and no Qdrant points were written.

At the initial startup checkpoint, the 4,096-token value was only a live server error observation. The later tokenizer/boundary checks below extend that evidence. Retrieval quality and full pipeline acceptance remain unverified. Near-unit norms on samples do not establish a universal normalization guarantee.

## Downloaded asset identity

The runtime manifest refers to mutable upstream `main` URLs. These local SHA-256 digests record the files actually downloaded; an immutable image alone does not pin remotely downloaded weights.

| File | SHA-256 |
| --- | --- |
| `model.safetensors` | `2192a98e3d88c07c21b1567fc8781ca79d7eed4ff64e7dbf2274c96b2b1b8e17` |
| `config.json` | `857d9d7c344207e79b804b16d77209ceb1c2c463698ecc6a3acf8509584551e7` |
| `tokenizer.json` | `0fb8bdddbd4c4ffa55e51d5b0393611e3df49dd86a31189ef5dcb750cf3da399` |
| `tokenizer_config.json` | `708b5b99ea78c9accab60816117f49c643b9b28016f8a40ccd320c245f974aba` |
| `special_tokens_map.json` | `94e708c3f5e64acf85bbe5ad01467a1248faadb73e83b41793087ecced586e8f` |
| `processor_config.json` | `462a02c8a594e7c9df811130433424101f71cdf83713d65d96451fec6eb32c11` |

The [embedding contract decision](../../.scratch/ingestion-pipeline/issues/09-vector-contract.md#answer) is resolved, including the user-approved heading context and exact storage/identity conventions. The [acceptance decision](../../.scratch/ingestion-pipeline/issues/11-acceptance-and-handoff.md#answer) is also resolved; these decisions do not establish live seed acceptance.

## Tokenizer, boundary and bounded-batch verification — 2026-09-18

The reproducible [probe](probes/embedding_contract.py) passed against the same cached image digest, NIM 2.3.0 / API 1.0.0 and downloaded tokenizer hash recorded above. [Machine-readable evidence](evidence/embedding-contract-20260918.json) contains generated harmless inputs, local/server counts, indices, vector validation, error messages and sample timings. No patient notes were read, no vectors were written to Qdrant, and no service configuration was changed during these probes.

| Measurement | Result |
| --- | --- |
| Tokenizer | `tokenizers==0.22.2`, loading the local `tokenizer.json` directly; padding and truncation disabled |
| Local counting rule | Encode `passage: ` or `query: ` followed by the exact submitted text, with the tokenizer's special-token postprocessor enabled |
| Special tokens | Tokenizer postprocessor adds one beginning-of-text token; no automatic end-of-text token |
| HTTP input | Submit the original text with explicit `input_type`; do not manually add the mode prefix, since the NIM adds it |
| Count agreement | All 16 sample requests matched local counts exactly: eight text forms tested in both modes |
| Boundary | Both modes accepted exactly 4,095 and 4,096 formatted tokens and rejected 4,097 with HTTP 422, `truncate: NONE` |
| Query limit distinction | Both 512- and 513-token queries passed; the downloaded processor's 512 setting is not this NIM's hard query limit |
| Bounded batches | 1, 8, 16 and 32 passages of 512 formatted tokens passed with complete unique response indices, finite nonzero 2,048-dimensional vectors and exact aggregate usage |
| Mixed valid/oversized batch | Entire request rejected with HTTP 422 and no partial vector response |

**Count the full formatted string rather than adding a fixed overhead.** For example, `word` has one content token and takes five passage tokens or four query tokens; `Café — temperature 37.2 °C.` has 12 content tokens and takes 14 passage tokens or 13 query tokens. Prefix-boundary token merges change the difference. The samples also cover headings, placeholders, repeated whitespace and literal special-token markers. This establishes agreement for the tested forms, not an exhaustive proof over all strings.

The approved content budget remains at most 512 tokens for the exact text submitted, including repeated sanitized heading context, counted without automatically added special tokens. Separately require the complete mode-formatted count to fit 4,096 and retain `truncate: NONE` at the server. The service can reject a count mismatch; never silently truncate to recover. Up to 64 body tokens may overlap a long section; offsets must refer to exact sanitized body text. The user accepted repeating the source heading on each split chunk; the [final contract](../../.scratch/ingestion-pipeline/issues/09-vector-contract.md#answer) owns exact input construction and separate heading/body citation offsets.

Use an initial operational client batch of eight chunks, one request at a time, within the tested range. This is a conservative implementation default, not the server maximum or a throughput claim. HTTP list size and the runtime's internal GPU batching are different limits. The report's single-run timings are diagnostic observations, not a performance benchmark.

Downloaded files advertise conflicting limits: `tokenizer_config.json` says 16,384, `processor_config.json` says passage 4,096 / query 512, and the README discusses 10,240. The downloaded Python processor also contains a duplicated passage prefix; it was not executed for these probes. Do not import that code or copy its truncation defaults as if it described the native NIM request path. The measured serving contract above controls admission for this deployment.

Reproduce from the repository root using an isolated package directory (no project dependency changes required):

```bash
python3 -m pip install --no-deps --target /tmp/p360-tokenizer-probe-20260918/packages 'tokenizers==0.22.2'
PYTHONPATH=/tmp/p360-tokenizer-probe-20260918/packages python3 backend/ingestion/probes/embedding_contract.py \
  --tokenizer /home/nvidia/.cache/nim/embed/weights/embed/tokenizer.json \
  --output /tmp/p360-embedding-contract-report.json
```

Source for the local tokenizer API: [Hugging Face Tokenizer reference](https://huggingface.co/docs/tokenizers/api/tokenizer). Serving behavior here is measured locally, not inferred from those API docs.

### Concurrent deployment drift observed

During this later check the running container again referenced `:latest`, although its actual image ID/digest still matched the inspected digest. Its Docker health check failed because `/bin/sh` was absent; HTTP readiness and all inference probes passed. The active mounts were the earlier `/opt/nim/.cache` path plus persistent `/model`, so the earlier compilation-cache fix was also no longer active. This differs from the successful startup/recreate checkpoint above and coincides with concurrent deployment edits. These probes left that configuration untouched. Restore the inspected digest reference, `/opt/cache` persistence and direct readiness command before claiming deployment acceptance; retain other sessions' changes.
