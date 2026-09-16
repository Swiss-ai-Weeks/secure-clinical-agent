# Deploying the hybrid RAG stack

> Checkout note: this document preserves the earlier RAG design and verification history. Its `scripts/` launchers and `tests/` suites are absent from this checkout; their commands are historical, not runnable setup instructions. See [the backend guide](../README.md) for the checked-in layout and Patient360 Compose commands.

> The user now requests fully local deployment. Follow [the staged local plan](SELF-HOSTED-PLAN.md) first. This runbook describes the existing hybrid implementation until stage 5 converts the launcher; its hosted-key steps are not prerequisites for the new plan.

Run commands on the LaunchPad server from `/home/nvidia/Documents/secure-clinical-agent`. The files use Docker Compose and the existing NVIDIA runtime; no Kubernetes or driver reinstallation is needed.

## 1. Prepare the pinned upstream code

```bash
cd /home/nvidia/Documents/secure-clinical-agent
./scripts/rag bootstrap
./scripts/rag validate
```

Bootstrap downloads NVIDIA RAG at the commit in `backend/deploy/blueprint.ref`, initializes the model cache, and generates private random object-store credentials. Re-running it preserves existing credentials. The vendor code, credentials, model cache, and uploaded documents are Git-ignored.

Validation renders the merged Compose configuration using a dummy key, checks the exact 13 active services, local retrieval endpoints, matching embedding settings, valid GPU IDs, storage mounts, scoped volumes, and localhost ports. It does not prove that models or the pipeline are running.

## 2. Configure NVIDIA access privately

For a walkthrough of the model page and how the Brev notebook gets its settings, see [Getting hosted inference access](INFERENCE-ACCESS.md). No Brev inference deployment needs to be created for this selected hosted-model setup.

Registry downloads and hosted inference are separate capabilities. One key may support both, but successful Docker login alone proves neither access to every image nor authorization for the selected hosted model.

```bash
./scripts/rag auth
./scripts/rag access
```

The wizard hides input and saves independently:

| Capability | Account page / permission | Private file |
|---|---|---|
| Container/model downloads | [NGC API Keys](https://org.ngc.nvidia.com/setup/api-keys), NGC Catalog, required image/model entitlements | `.secrets/ngc.env`: `NGC_API_KEY` |
| Hosted answers | [Configured NVIDIA model page](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b), API access / Public API Endpoints | `.secrets/llm.env`: `APP_LLM_APIKEY` |

Enter reuses a saved key. If no hosted key exists, Enter tests the registry key for hosted access. A hosted403 preserves the successfully saved registry key and any earlier hosted key. Credential files have mode0600 and are Git-ignored. Do not paste keys into chat.

`access` checks every active image manifest and performs synthetic hosted generation. It reports all image denials before returning failure; a successful manifest check does not prove access to model artifacts downloaded during startup.

**Current account blocker:** your saved key authenticates Docker, but six pinned images return `Payment Required`, and hosted inference returns HTTP403 `Authorization failed`. You confirmed an existing entitlement. Ask your NVIDIA/LaunchPad administrator to confirm that it is active for the organization and user behind this key and covers the denied images listed in [the verification record](VERIFICATION-REVIEW.md). Separately check the Public API Endpoints role and access to the configured model. This evidence does not establish the precise account-side cause and does not imply you need another purchase. [NVIDIA documents account roles and endpoint access](https://docs.nvidia.com/ngc/latest/ngc-user-guide.html).

After the account mapping is corrected, rerun `auth` if the key changed, then `access`. Repeatedly entering the same unauthorized key cannot repair entitlement mapping in this script.

## 3. Start the services

```bash
./scripts/rag up
```

Startup checks GPU/runtime/disk prerequisites, the rendered architecture contract, every image manifest, and hosted-model authorization before creating model containers. It then starts local model services, storage, extraction workers, APIs, and the UI in that order. The first run downloads model weights and container images and can take tens of minutes. Model profiles and real GPU memory use are only confirmed during startup.

If hosted access is still being resolved but all image entitlements work, `./scripts/rag local-up` starts the local stack and checks local readiness. It deliberately leaves hosted inference unverified.

To inspect progress from another terminal:

```bash
./scripts/rag status
./scripts/rag logs nemotron-vlm-embedding-ms
nvidia-smi
```

You can start the storage layer before you have an NVIDIA key:

```bash
./scripts/rag storage-up
```

This starts only Elasticsearch, SeaweedFS, and Redis. It is useful preparation, but not a working RAG application.

## 4. Verify readiness and hosted inference

```bash
./scripts/rag health
```

This requires all 13 project containers to be running and healthy, including the six local NIMs; it checks both API dependency reports, the web page, and an actual NVIDIA-hosted generation request with a synthetic prompt. Missing or skipped required local dependencies fail. Use `./scripts/rag health-local` for local checks only. The extra hosted request is necessary because an upstream health report can label remote services healthy without exercising your credentials.

Local addresses after successful startup:

| Service | Address |
|---|---|
| Web UI | http://127.0.0.1:8090 |
| RAG API docs | http://127.0.0.1:8081/docs |
| Ingestor API docs | http://127.0.0.1:8082/docs |

When connecting from a laptop, forward port 8090 using the remote IDE's Ports panel, or use your existing SSH connection:

```bash
ssh -N -L 8090:127.0.0.1:8090 nvidia@YOUR_EXISTING_SSH_HOST
```

Use your actual SSH host/configuration; `YOUR_EXISTING_SSH_HOST` is a placeholder. Then open http://localhost:8090 on your laptop. The UI proxies API calls internally, so the API ports need forwarding only if you want to call them directly. No public ingress is configured.

## 5. Verify document ingestion and retrieval

Run the automated acceptance client:

```bash
./scripts/rag smoke
```

It creates a unique `rag_smoke_*` collection, uploads `backend/examples/demo.txt` with summaries disabled, rejects partial ingestion even on HTTP200, and requires local search with reranking to return **ALPINE-742** from **demo.txt**. It then calls generation through the UI proxy, accumulates the streamed answer, and requires both the known fact in the answer and a matching source citation. An incomplete stream fails. No existing collections are deleted.

Each run writes its collection name and completed checks to `.data/verification/<collection>.json`. A failed run keeps `complete_pipeline: false`. This evidence contains only the synthetic test fixture and result. `./scripts/rag smoke --retrieval-only` stops after local search and explicitly does not verify hosted generation.

After a successful smoke test, verify persistence using its printed collection name:

```bash
./scripts/rag down
./scripts/rag up
./scripts/rag smoke --reuse rag_smoke_REPLACE_WITH_PRINTED_SUFFIX
```

`--reuse` skips upload, so success establishes that the indexed fixture survived removal and recreation of the project's containers. Use the actual lowercase collection name printed by the first run. This step has **not** run successfully yet because the full stack is blocked on NVIDIA access.

The same workflow is available in the UI: upload the synthetic file, wait for ingestion, then ask “What is the project test code?” and inspect the answer and source. This text test does not exercise scanned PDFs or complex table/chart extraction. The NIM readiness probes cover service availability; representative synthetic PDFs are a later acceptance gate before document-format customization.

## Automated regression checks

```bash
python3 -m unittest discover -s tests -v
./scripts/rag validate
bash -n scripts/rag scripts/nvidia-setup-wizard.sh
```

The tests cover credential preservation, separate-key routing through the actual launcher, upstream image/service/GPU/port contracts, negative configuration mutations, required readiness, image-access failures, and upload/search/SSE answer parsing. External services are mocked except for the real Compose renderer. Passing these tests is not a claim that live ingestion or inference succeeds.

## Configuration and persistence

Edit `backend/deploy/hybrid.env` for model names, GPU assignments, and retrieval settings. Edit `backend/deploy/compose.hybrid.yaml` for container settings. Use `./scripts/rag validate` and then `./scripts/rag up` after changes. Do not source NVIDIA's `nvdev.env`: it also redirects embeddings and extraction to cloud APIs, which is different from this selected hybrid setup.

Docker volumes are named `secure-clinical-agent-rag-vol-*`; they persist Elasticsearch indices, SeaweedFS artifacts, Redis state, and application scratch data. Local models are cached in `.cache/models/`. These reside on this server and need separate backup if the LaunchPad environment expires. Keep `.secrets/storage.env` and `.secrets/s3.json` together; they contain matching object-store credentials.

```bash
./scripts/rag down
```

This removes this project's containers and network while retaining data volumes and model cache. It does not stop the existing LaunchPad containers or Kubernetes components. There is no destructive reset command.

## Common startup failures

| Symptom | Next check |
|---|---|
| `NGC_API_KEY is missing` | Run `./scripts/rag auth` in your interactive terminal |
| Image pull or model download denied | Check NGC Catalog permission and model entitlement; rerun `auth` after correcting access |
| Hosted inference returns 401/403 | Check Public API Endpoints permission and whether the key can invoke the selected model |
| Hosted inference returns 429 | Wait for the API limit to reset or use your organization's provisioned endpoint |
| NIM is starting for a long time | Inspect its logs and `.cache/models/`; initial downloads can take tens of minutes |
| Out-of-memory on a GPU | Inspect `nvidia-smi`, other workloads, and model-selected profiles before changing GPU assignments |
| UI works but no documents are found | Check ingestion completion and collection selection; changing the embedding model requires re-indexing |
| Localhost URL fails on your laptop | Forward the server's port 8090 first |

## Verification record — 2026-09-15

- **Passed:** 51 automated tests, independent source review, merged Compose validation, Bash/Python checks.
- **Live storage passed:** three healthy containers; Elasticsearch green; Redis append-only persistence enabled; authenticated S3 bucket-list HTTP200.
- **Live access failed:** six pinned image manifests denied with `Payment Required`; hosted synthetic generation HTTP403. `access` returns nonzero with separate diagnoses.
- **Startup protection passed:** `local-up` passed host/config checks and stopped at image entitlement checks before creating a partial model deployment.
- **Readiness and smoke correctly fail:** required containers and API/UI connections are missing. No synthetic collection was created; its failed-attempt evidence has `complete_pipeline: false`.
- **Pending:** image/model downloads, all NIM/application readiness, successful document upload/search/answer/citation, UI proxy round trip, and restart persistence of an indexed fixture.

See [the detailed independent review](VERIFICATION-REVIEW.md) and the implementation plan (local-only record: `../../.scratch/rag-blueprint-reliability/spec.md`; not published). The operating system is Ubuntu 24.04.3; upstream's documented OS baseline is 22.04.

Reference deployment guides: [self-hosted models](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/docs/deploy-docker-self-hosted.md), [NVIDIA-hosted models](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/docs/deploy-docker-nvidia-hosted.md). This repository combines their local retrieval and hosted generation settings.
