# Getting hosted inference access

> Checkout note: this document preserves the earlier RAG design and verification history. Its `scripts/` launchers and `tests/` suites are absent from this checkout; their commands are historical, not runnable setup instructions. See [the backend guide](../README.md) for the checked-in layout and Patient360 Compose commands.

The current design calls a model already running on NVIDIA's hosted API. Creating an inference deployment in Brev is not a prerequisite. Brev/LaunchPad supplies the GPU environment for the local application and retrieval services; the NVIDIA API Catalog supplies hosted generation.

## Get the hosted key

1. Open the [Nemotron model Build page](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/build).
2. Sign in with your NVIDIA account. Under **Prototype**, click **Generate API Key**. These labels and the hosted endpoint were verified on the public model page on 2026-09-15.
3. Complete any verification, terms, or account-access steps the signed-in page requests. Those account-specific screens are not visible to the assistant. If the option is denied, record the error text, without the key.
4. Copy the generated key into the wizard's **hosted inference key** prompt. If the wizard has exited, run `./scripts/rag auth`; Enter at the registry stage reuses the saved registry key, then enter the newly generated hosted key at the hosted stage.
5. The wizard sends a synthetic request to the configured model and saves `.secrets/llm.env` only if it receives an answer. A success here proves hosted inference works; a403 is an authorization failure, not evidence that a Brev deployment is missing.

The model page shows the endpoint `https://integrate.api.nvidia.com/v1` and model identifier `nvidia/nemotron-3-super-120b-a12b`. The private key authorizes requests to that existing endpoint. It does not launch a model on this machine.

After hosted access succeeds, `./scripts/rag access` checks both hosted inference and every required container image. The six previously denied images are a separate local-deployment gate; hosted-key success alone does not resolve them. Once access checks pass, run `./scripts/rag up` and `./scripts/rag smoke`.

## What the reference notebook does automatically

Inspected source: `.vendor/nvidia-rag/notebooks/launchable.ipynb` at pinned commit `f20716d73ae69a544ad4a692f38d6178a64e6f36`. This is NVIDIA's reference notebook, not a recovered copy from the user's live Brev instance.

| Notebook section | Actual source behavior |
|---|---|
| 2.1 Set Your NGC API Key | Requires NGC Catalog, Public API Endpoints, and hosted-model access |
| Key-entry cell (zero-based cell 14) | Reuses `NGC_API_KEY` from the notebook process if its value starts with `nvapi-`; otherwise prompts privately. This prefix check alone does not prove authorization. |
| 2.3 Login / configure (cell 18) | Logs Docker into NGC and writes generation settings for the hosted Nemotron model |
| Setup helpers (cell 5) | Selects six local retrieval/extraction NIMs and explicitly excludes the local LLM from this launchable path |
| 2.4 Deploy All Services | Calls `deploy_all()` to orchestrate Docker services |

The default notebook generation URL is empty, selecting the upstream hosted-client default. Our configuration supplies the NVIDIA hosted URL explicitly. The notebook selects the text embedding model; our adaptation selects the blueprint's vision-capable embedding model. Neither difference creates a hosted inference deployment in Brev.

An already populated key could explain why credential setup appeared automatic. Brev supports launch-time parameters and organization secrets, but we have not verified that either supplied this particular notebook's key. The reference notebook can also clone the `develop` branch, so a running launchable may differ from our pinned version.

## Inspecting your specific Jupyter instance

The supplied Jupyter root and `/api/contents` both returned HTTP403 from the assistant's environment. The notebook contents and live model configuration could not be read. That Jupyter403 is separate from the hosted inference403 seen in the wizard.

To make the exact source available locally, open the notebook in your signed-in browser, download the `.ipynb` file from Jupyter's file browser, remove any pasted credential values and saved outputs containing credentials, and place it at `reference/brev-launchable.ipynb`. The assistant can then compare its setup cells, model choices, repository revision, and deployment commands with our configuration. A notebook file alone does not reveal the current kernel environment or prove its services are running.

If the notebook is still running, this cell reports only whether credential variables exist, never their values:

```python
import os
for name in ('NGC_API_KEY', 'NVIDIA_API_KEY', 'APP_LLM_APIKEY'):
    print(name, 'present' if os.environ.get(name) else 'not present')
```

## Sources

- [NVIDIA model Build page: Prototype, Generate API Key, and endpoint example](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/build)
- [Pinned reference launchable notebook](https://github.com/NVIDIA-AI-Blueprints/rag/blob/f20716d73ae69a544ad4a692f38d6178a64e6f36/notebooks/launchable.ipynb)
- [Brev Launchables: setup values, organization secrets, and secure links](https://docs.nvidia.com/brev/concepts/launchables)
