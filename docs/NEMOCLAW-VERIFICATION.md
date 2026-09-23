# NemoClaw reliability verification

The reported failure was an unavailable assistant after authorized note retrieval. A green backend health response alone did not verify that the agent could start or answer.

## Findings and fixes

1. **Docker network mismatch:** Nano was reachable from the OpenShell network, but NemoClaw's onboarding probe runs on Docker's default bridge. That probe failed, making sandbox creation return HTTP 503. The checked-in `compose.openshell-tools.yaml` now publishes Nano to both bridge gateways while retaining the loopback binding from the base Compose file.
2. **Concurrent onboarding:** Different sessions attempted onboarding simultaneously, but NemoClaw shares onboarding recovery state and rejects the second owner. The adapter now serializes cold provisioning while retaining separate session locks and sandbox reuse. NemoClaw CLI calls also share a gate because agent execution, cleanup, and status work use the same host lifecycle fence; a regression covers startup alongside an active agent command.
3. **Dashboard port exhaustion:** The installed CLI's automatic pool has only eleven ports (18789–18799), all occupied on this host. Session onboarding now passes an available OS-assigned host port through the supported `--control-ui-port` option. Existing sandboxes and the protected `patient360` sandbox were preserved.
4. **Premature startup timeout:** Chat was giving a cold sandbox only 20 seconds. It now uses the adapter client's existing 600-second startup allowance. A transport simulation verifies that a 90-second cold start proceeds to credentials and the agent turn.
5. **Failed CLI output treated as success:** The adapter accepted usable-looking stdout even when the agent process exited unsuccessfully. Nonzero exit status now produces an error response without an answer.
6. **Sandbox status mistaken for absence:** NemoClaw status can fail while host lifecycle locks are held. Readiness now queries the OpenShell gateway directly. Only an explicit sandbox-not-found response permits creation; gateway failures and existing non-ready sandboxes do not trigger another onboarding run.
7. **Uncited model output:** A real browser response contained a summary but no matching citation token. The adapter now explicitly requests square-bracket citations, verifies a note reference against the authorized tool result, and permits one correction through NemoClaw. A second uncited result fails instead of receiving an invented source link.
8. **Hidden startup failure and duplicate UI message:** Startup failures now produce a sanitized warning and a retrieval step. The Ask panel displays the unavailable explanation once and supports retry to a cited answer.

Earlier fixes in this debugging session preserved the actual run JWT during note retrieval, allowed a short bounded retry for credential propagation, rejected tool error payloads as evidence, and aligned note citation identifiers between the adapter and chat.

Concurrent workspace changes included inline citation buttons and briefly a direct Nemotron fallback; the latest chat source has removed that fallback. Unrelated workspace edits were preserved. Live NemoClaw verification requires the `OpenShell sandbox turn` retrieval step and rejects a direct Nemotron fallback. UI tests scope citation counts to the Sources used section. The visit-summary regression checks the current admission note is included and the historical pneumonia note is excluded.

## Test plan and execution

Live infrastructure run: **3 tests passed in 168.65 seconds**, including two simultaneous new-session requests and subsequent reuse. **Later cold starts failed again; this one passing run does not establish reliable startup.**

Latest deterministic run: **351 backend tests passed**, with **7 integration cases deselected**. The **18 affected frontend tests passed**, the production build passed, and Ruff passed for the touched backend/runtime files. Live results are recorded separately below.

Tests use the public adapter HTTP endpoints, backend `/chat`, and rendered Ask panel. Simulated failures mock external CLI or HTTP boundaries; live checks use Docker, actual sandboxes, the credential proxy, the local model, and a browser.

| Check | Evidence before fix | Verification |
| --- | --- | --- |
| Model reachable during onboarding and from sandbox network | Default bridge failed; OpenShell bridge passed | Both real network probes passed |
| Concurrent new sessions and sandbox reuse | HTTP 503: another onboarding run owns the lock | Deterministic regression passed; live startup/reuse passed once, but later cold starts failed inside NemoClaw bootstrap |
| Startup with default dashboard pool full | Real HTTP 503 and deterministic regression failed | Deterministic regression passed; live startup/reuse passed once, but later cold starts failed inside NemoClaw bootstrap |
| Sandbox reuse during host lifecycle work | Real reuse failed after a status error caused another onboard attempt | HTTP regressions passed: ready sandbox reused; gateway outage never creates another sandbox |
| Cold start budget | `/chat` refused after simulated startup exceeded 20 seconds | Regression passed with normal startup allowance |
| Agent process errors and timeouts | Nonzero process with answer-like stdout returned HTTP 200 | HTTP regressions passed: error response, no answer |
| Protected sandbox | Session turns must not use the gold sandbox | HTTP regression passed without invoking the CLI |
| Startup diagnostics | Missing retrieval step | Regression passed; private error body excluded from logs |
| UI outage and retry | Unavailable sentence appeared twice | Duplicate-message and retry regressions passed |
| Uncited note output | Live answer omitted its source token; deterministic test reproduced HTTP 200 | Correction succeeds only with an authorized citation; repeated omission returns an error |
| Browser through the real UI | Must not accept fallback as agent success | **Failed**: both final browser cases refused during sandbox setup; four successful cited turns are not verified |

### Repeat deterministic checks

From `backend/app`:

```bash
.venv/bin/pytest -o cache_dir=/tmp/p360-pytest-cache -m 'not integration' -q
.venv/bin/ruff check --no-cache --config pyproject.toml \
  tests/test_nemoclaw_http.py tests/test_chat_runtime_failures.py \
  tests/integration/test_nemoclaw_live.py patient360/chat.py \
  ../deploy/patient360/nemoclaw-turn.py
```

From `frontend`:

```bash
npm run test:unit -- --run tests/unit/askPatient360Panel.spec.ts tests/unit/askCitations.spec.ts
npm run build
```

### Repeat live checks

These require the running local deployment. The tests create isolated sessions and request cleanup of their own session sandboxes afterward. They do not reseed records or alter consent.

From `backend/app`:

```bash
PATIENT360_LIVE_NEMOCLAW=1 .venv/bin/pytest \
  -o cache_dir=/tmp/p360-pytest-cache tests/integration/test_nemoclaw_live.py -v
```

From `frontend`:

```bash
PATIENT360_LIVE_NEMOCLAW=1 npx playwright test \
  tests/e2e/nemoclaw-live.spec.ts --project=chromium --workers=1 --reporter=line
```

Optional environment overrides: `PATIENT360_ADAPTER_TEST_URL`, `PATIENT360_LIVE_UI_URL`, and `PATIENT360_LIVE_PATIENT_KEY`. The browser default uses the Norman Hettinger chart from this deployment.

## Remaining live failure and coordination needed

The latest complete startup probe returned HTTP 503 after 111.8 seconds. Full NemoClaw output showed a sandbox entering OpenShell `Error` phase during managed bootstrap. The final error was `Sandbox post-create verification or finalization failed; automatic sandbox cleanup was not safe`. Its diagnostic recorded `selected_gpu_route=none` and `selected_gpu_mode=persistent sandbox startup command`; the generic “Docker GPU patch failed” headline does not establish a GPU hardware problem. Do not bypass sandbox checks or force-remove containers based on that headline.

This run also overlapped other activity on the shared deployment: source edits, a backend restart, an adapter restart at 22:06:17 UTC on 2026-09-21 that disconnected an in-flight diagnostic, and a separate NemoClaw process deleting existing sandboxes. That activity prevents a stable end-to-end verdict. One earlier browser request did complete a real NemoClaw turn, but lacked a citation; the correction is covered by deterministic tests, not yet a passing four-turn live run.

The next required step is a quiet deployment window, then rerunning the documented live tests and investigating any remaining bootstrap Error state with immutable container identities. Temporary code tracing was removed. The redacted final diagnostic is in `.cache/nemoclaw-reliability/onboard-diagnostic-latest.txt`; the upstream diagnostic directory is `/home/nvidia/.nemoclaw/onboard-failures/2026-09-21T22-09-19-090Z-p360-s-a83ef6fc7dee-docker-gpu-patch`.

## Running this deployment

Use the existing local `.env`; do not overwrite its credentials. From the repository root, the network overlay is required for both the backend tool endpoint and Nano inference:

```bash
docker compose --env-file backend/deploy/patient360/.env \
  -f backend/deploy/patient360/compose.yaml \
  -f backend/deploy/patient360/compose.openshell-tools.yaml \
  up -d --build --no-deps backend nano
systemctl --user restart patient360-nemoclaw-turn.service
```

The systemd user service already exists on this host. On other hosts, install/configure the host adapter using the deployment scripts first. Bridge addresses default to `172.17.0.1` for Docker and `172.20.0.1` for OpenShell; override `PATIENT360_DOCKER_GATEWAY` and `PATIENT360_SANDBOX_GATEWAY` when those networks use different gateways.

The running UI is **http://localhost:4173** on this machine (or **http://172.16.0.157:4173** from a machine that can reach this host). To start the frontend manually:

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 4173
```

Select **Dr. Sarah Chen**, open **Norman Hettinger**, choose **Ask Patient360**, enter **Summarize the latest note**, and select **Ask with sources**. A new session can take minutes while its sandbox starts; follow-up questions reuse that sandbox.

This is a local deployment check, not a long-duration load or availability certification. Cold provisioning and NemoClaw CLI access are serialized, and enough queued sessions can still exceed the request deadline. The locks coordinate this adapter process; separate manual CLI processes are not covered. The free-port handoff is validated by NemoClaw and can fail if another process takes the selected port before onboarding reserves it.
