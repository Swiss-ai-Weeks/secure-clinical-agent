"""Opt-in checks against the real Patient360 deployment, not mocked agent calls."""

import json
import os
import subprocess

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PATIENT360_LIVE_NEMOCLAW") != "1",
        reason="set PATIENT360_LIVE_NEMOCLAW=1 to verify the running deployment",
    ),
]


@pytest.mark.parametrize(
    "network,gateway",
    [("bridge", "host-gateway"), ("openshell-docker", "172.20.0.1")],
    ids=["onboarding-probe", "agent-sandbox"],
)
def test_model_reachable_from_onboarding_and_sandbox(network, gateway):
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            "--add-host",
            f"host.openshell.internal:{gateway}",
            "curlimages/curl:8.13.0",
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            "5",
            "http://host.openshell.internal:8000/v1/models",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"{network}: {result.stderr}"
    body = json.loads(result.stdout)
    assert "nvidia/nemotron-3-nano" in {model["id"] for model in body["data"]}


def test_two_sessions_start_concurrently_and_reuse_sandboxes():
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    import httpx

    url = os.environ.get("PATIENT360_ADAPTER_TEST_URL", "http://127.0.0.1:17999")
    sessions = [uuid4().hex + uuid4().hex for _ in range(2)]
    expected = [f"p360-s-{sid[:12]}" for sid in sessions]

    def start(sid):
        response = httpx.post(f"{url}/v1/sandboxes", json={"sid": sid}, timeout=650, trust_env=False)
        assert response.status_code == 200, response.text
        return response.json()["sandbox_id"]

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            names = list(workers.map(start, sessions))
        assert len(set(names)) == 2
        for sid, name in zip(sessions, names, strict=True):
            assert start(sid) == name
    finally:
        for name in expected:
            response = httpx.delete(f"{url}/v1/sandboxes/{name}", timeout=30, trust_env=False)
            assert response.status_code == 202, response.text
