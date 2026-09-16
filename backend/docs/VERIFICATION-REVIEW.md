# Independent verification of the NVIDIA RAG adaptation

> Checkout note: this document preserves the earlier RAG design and verification history. Its `scripts/` launchers and `tests/` suites are absent from this checkout; their commands are historical, not runnable setup instructions. See [the backend guide](../README.md) for the checked-in layout and Patient360 Compose commands.

Verification date: 2026-09-15. Scope: the pinned NVIDIA RAG core workflow, with local extraction, embeddings, reranking and storage, and NVIDIA-hosted answer generation. This is a two-GPU hybrid adaptation, not activation of every optional branch of NVIDIA's diagram.

## Independent evidence and initial defects

The verifier rendered the actual four upstream Compose files plus this repository's override using deliberately fake registry, hosted and storage credentials. No credential files were opened, models invoked, containers started or live data changed by these tests. `tests/test_deployment_contract.py` contains the independent executable contract.

The initial run reproduced eight validator blind spots: it accepted incorrect GPU placement, empty GPU IDs, an incorrect GPU driver, disabled citations, disabled reranking, the wrong vector-store type, an incorrect API container port, and enabled query rewriting. It also found no explicit readiness healthcheck for `graphic-elements`; without a healthcheck Compose `--wait` can establish only that a container is running. These findings were sent to the implementation agent before fixes.

The actual initial configuration nevertheless matched the chosen 13-service topology, pinned image versions, exact six-model GPU placement, local retrieval/extraction endpoints, and loopback published ports. The upstream Compose configuration already supports a separate `APP_LLM_APIKEY`; the original auth flow failed to expose that supported distinction.

## Independent retest checkpoint

After the first implementation fixes, the verifier independently ran `python3 -m unittest discover -s tests -v`: **35 tests passed**. This checkpoint includes 12 independent deployment/launcher tests, 20 authentication tests and three health-response tests. All eight previously accepted configuration mutations now fail as required, and all 13 active services now have explicit healthchecks. Two additional black-box tests execute the actual launcher against an isolated temporary repository with fake key files and a fake Docker status command: separate hosted-key routing and legacy single-key fallback both pass.

This is a static/unit checkpoint, not a successful deployment claim. Live image pulling, actual NIM probe availability, GPU memory fit, authenticated hosted inference, and document ingestion/answer/citation proof remain the deployment agent's runtime gates. Additional implementation and tests may follow this checkpoint.

## Final independent review and live blockers

The final independent run completed **51 tests successfully in 2.955 seconds**: 12 independent deployment/launcher tests, 20 auth tests, eight smoke-client regression tests, six image-access tests and five readiness tests. These tests verify real Compose rendering and controlled protocol/error-handling behavior; they do not run a live complete RAG pipeline. Mock readiness results are not observations about this server.

Final source review confirmed that startup executes the architecture contract and image-access gates before starting containers, full startup also verifies hosted authorization, and local health requires all 13 containers to be running and healthy in addition to required application dependencies. The smoke client matches the pinned upload, search, SSE generation and frontend proxy interfaces. A normal SSE finish, the fact in the accumulated answer, and matching filename/content in citations are separate acceptance requirements. No blocking code-review finding remained at this checkpoint.

The deployment agent's recorded live image-access results (local-only record: `../../.scratch/rag-blueprint-reliability/image-access.json`; not published), inspected by the verifier, report `Payment Required` for six pinned images:

- `page-elements`
- `graphic-elements`
- `table-structure`
- `nemotron-ocr`
- `nemotron-ranking-ms`
- `nv-ingest-ms-runtime`

The embedding image and three application images were accessible in that record; storage images were recorded as already running public images. Registry login success does not grant entitlement to every image. The user reports existing entitlement, so the next action is to reconcile the selected NVIDIA organization, user/team membership, key permissions and image-specific entitlement assignment with that entitlement, using the recorded image names/tags. This result does not establish that another purchase is required.

Hosted inference separately returned HTTP 403 with the configured key/model. That authorization gate must pass independently. The actual six NIMs, extraction runtime, complete document pipeline and scanned PDF/table/chart fixtures remain unverified while those access failures persist. The deployment runbook and plan contain the steps to resume after account access is corrected.

## Acceptance matrix

| Gate | Required proof | What it does not prove |
|---|---|---|
| Upstream provenance | Vendor HEAD is `f20716d73ae69a544ad4a692f38d6178a64e6f36` (v2.6.2), tracked vendor files unmodified; core service images match the pin | Container availability or model entitlement |
| Architecture contract | Exactly 13 active services; extraction on GPU 0 and embeddings/reranking on GPU 1; NVIDIA GPU reservations; local stores and retrieval endpoints; hosted generation endpoint; citations and reranking enabled; optional branches disabled | GPU memory fit or runtime behavior |
| Credential isolation | Fake registry key reaches NIM download configuration; different fake hosted key reaches generation and summary key configuration | Either real key is authorized |
| Auth regression | Successful registry auth survives a subsequent hosted HTTP 403; explicit hosted key is supported; 401/403/429/network failures remain failures with distinct diagnostic meaning; no secret appears in output | Actual hosted model authorization |
| Validator rejection | Mutating the configuration away from the contract causes a nonzero result; false success cannot arise from wrong GPU placement, endpoints, ports or enabled features | Runtime correctness |
| Local readiness | Every active service has a real readiness probe; live model endpoints and required application dependency statuses are healthy; UI HTTP 200 | Ingestion and answer correctness |
| Hosted readiness | A real authenticated synthetic request to the configured model returns nonempty generated text using the selected hosted credential | Source retrieval or citation correctness |
| Document workflow | Create an isolated test collection; upload a synthetic document; confirm ingestion success; search returns its unique fact; generated answer contains that fact and cites its filename | Scanned PDF/table/chart extraction |
| Multimodal extraction | Representative synthetic scanned PDF, table and chart fixtures ingest successfully and their known facts can be retrieved with source citations | Accuracy on all clinical documents |
| Repeatability | Running validation/tests again passes; rerunning credential setup preserves known-good values on failure; restart retains indexed data and stored artifacts | Backup recovery, availability or production security |

The text smoke test must retrieve a distinctive synthetic fact from the expected document, then require it independently in the generated answer and in a matching citation. A plausible answer without the expected source citation is a failure. The ingestion endpoint returning HTTP 200 alone is not evidence that indexing completed successfully. Mocked HTTP tests validate error handling and protocol interpretation; they must never be recorded as successful live integration.

## Credential failure interpretation

The supplied transcript proves successful Docker registry authentication followed by HTTP 403 from a hosted inference request. These are different service authorizations. It does not prove that the key was typed incorrectly, that the selected model is available to that account, or that simply retrying the same key will fix access. Preserve the known-good registry credential and test an independently authorized hosted key against the configured model. A returned 403 remains an account/endpoint-access blocker until a real request succeeds.

## Commands

```bash
python3 -m unittest discover -s tests -p test_deployment_contract.py -v
python3 -m unittest discover -s tests -v
./scripts/rag validate
```

The independent contract invokes Docker Compose to render configuration only. It requires the pinned vendor checkout and initialized bind-mount directories from bootstrap. The live deployment, health and end-to-end commands are documented in the deployment runbook; their results must be recorded separately.

## Sources

- [Pinned upstream architecture and workflow](https://github.com/NVIDIA-AI-Blueprints/rag/tree/v2.6.2)
- [Pinned model services](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/deploy/compose/nims.yaml)
- [Pinned RAG server service-specific keys](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/deploy/compose/docker-compose-rag-server.yaml)
- [Pinned ingestor configuration](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/deploy/compose/docker-compose-ingestor-server.yaml)
- [Pinned health implementation](https://github.com/NVIDIA-AI-Blueprints/rag/blob/v2.6.2/src/nvidia_rag/rag_server/health.py)

These primary sources were inspected from the local pinned vendor checkout.
