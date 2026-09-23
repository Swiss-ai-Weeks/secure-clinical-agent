# NeMo Guardrails (second wall)

`LLMRails.check_async` runs this pack on every `/chat` turn. It does not generate the answer. OpenShell still writes that.

- Input: `check identity claim`, then the content-safety NIM when `PATIENT360_SAFETY_URL` is set.
- Output: `check citation leak` (ids must be in this run's tool results), then content safety when that URL is set.
- Compose service `safety` is that NIM (`PATIENT360_SAFETY_URL`, host port 8002).
- An empty safety URL drops the content-safety flows, so unit tests do not need a GPU. A set URL that errors refuses with `content_safety_unavailable`.

The identity and citation checks themselves stay in `patient360/guardrails.py` and are registered as Colang actions.
