"""Public adapter HTTP contracts with only the external NemoClaw CLI simulated."""

import importlib.util
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def adapter_http(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "deploy/patient360/nemoclaw-turn.py"
    spec = importlib.util.spec_from_file_location("adapter_http_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/test/bin/{name}")
    monkeypatch.setattr(module, "_project_run_token_placeholder", lambda name: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
        yield module, client
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def test_failed_agent_process_never_becomes_a_successful_answer(adapter_http, monkeypatch):
    module, client = adapter_http

    def failed_cli(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout='{"answer":"Partial response from a failed turn."}',
            stderr="agent process failed",
        )

    monkeypatch.setattr(module.subprocess, "run", failed_cli)
    response = client.post("/v1/turns", json={"sandbox": "p360-s-abcdef123456", "input": "Summarize notes"})

    assert response.status_code == 502
    assert "answer" not in response.json()
    assert "exited with code 1" in response.json()["detail"]


def test_replay_invalid_keeps_a_finished_answer(adapter_http, monkeypatch):
    import json

    module, client = adapter_http

    def replay_cli(command, **kwargs):
        if len(command) > 2 and command[2] == "agent":
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=json.dumps(
                    {"result": {"payloads": [{"text": "Latest note: mood improved [note_1]."}], "meta": {"replayInvalid": True}}}
                ),
                stderr="The agent turn did not complete: replayInvalid=true.",
            )
        raise AssertionError("Unexpected CLI operation")

    monkeypatch.setattr(module.subprocess, "run", replay_cli)
    response = client.post(
        "/v1/turns", json={"sandbox": "p360-s-abcdef123456", "input": "Summarize notes"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "Latest note: mood improved [note_1]."


def test_agent_timeout_returns_failure_without_an_answer(adapter_http, monkeypatch):
    module, client = adapter_http

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", timeout)
    response = client.post("/v1/turns", json={"sandbox": "p360-s-abcdef123456", "input": "Summarize notes"})

    assert response.status_code == 502
    assert response.json()["error"] == "TimeoutExpired"
    assert "answer" not in response.json()


def test_history_cannot_smuggle_an_evidence_blob(adapter_http, monkeypatch):
    module, client = adapter_http

    def unexpected_cli(command, **kwargs):
        pytest.fail("An evidence blob must be rejected before a turn runs")

    monkeypatch.setattr(module.subprocess, "run", unexpected_cli)
    response = client.post(
        "/v1/turns",
        json={
            "sandbox": "p360-s-abcdef123456",
            "input": "What about the dose?",
            "history": [{"role": "user", "content": "Summarize the latest note"}],
            "evidence": {"labs": ["secret-blob"]},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "evidence_not_allowed"
    assert "secret-blob" not in response.text


def test_protected_sandbox_cannot_be_used_for_a_session_turn(adapter_http, monkeypatch):
    module, client = adapter_http

    def unexpected_cli(command, **kwargs):
        pytest.fail("A protected sandbox must not execute a clinical turn")

    monkeypatch.setattr(module.subprocess, "run", unexpected_cli)
    response = client.post("/v1/turns", json={"sandbox": "patient360", "input": "Summarize notes"})

    assert response.status_code == 403
    assert response.json()["error"] == "protected_sandbox"
    assert "answer" not in response.json()

    credentials = client.post(
        "/v1/credentials", json={"sandbox": "patient360", "name": "RUN_TOKEN", "value": "not-a-token"}
    )
    assert credentials.status_code == 403
    assert credentials.json()["error"] == "protected_sandbox"


def test_concurrent_new_sessions_and_reuse_do_not_race_onboarding(adapter_http, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    module, client = adapter_http
    ready = set()
    onboarding = threading.Lock()
    started = []

    def cli(command, **kwargs):
        if command[1] == "onboard":
            name = command[command.index("--name") + 1]
            if not onboarding.acquire(blocking=False):
                return subprocess.CompletedProcess(command, 1, "", "another onboarding run owns the lock")
            try:
                started.append(name)
                sleep(0.1)
                ready.add(name)
            finally:
                onboarding.release()
        elif command[1:3] == ["sandbox", "get"]:
            exists = command[3] in ready
            return subprocess.CompletedProcess(
                command, 0 if exists else 1, '{"phase":"Ready"}' if exists else "", "sandbox not found"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    sessions = ["a" * 64, "b" * 64]

    def start(sid):
        return client.post("/v1/sandboxes", json={"sid": sid})

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(start, sessions))
    assert [response.status_code for response in responses] == [200, 200]
    names = [response.json()["sandbox_id"] for response in responses]
    assert len(set(names)) == 2
    for sid, name in zip(sessions, names, strict=True):
        assert start(sid).json()["sandbox_id"] == name
    assert sorted(started) == sorted(names), "Reusing a sandbox must not run onboarding again"


def test_session_starts_when_default_dashboard_range_is_full(adapter_http, monkeypatch):
    module, client = adapter_http
    ready = False

    def cli(command, **kwargs):
        nonlocal ready
        if command[1] == "onboard":
            if "--control-ui-port" not in command:
                return subprocess.CompletedProcess(
                    command, 1, "", "All dashboard ports 18789-18799 are occupied"
                )
            port = int(command[command.index("--control-ui-port") + 1])
            assert 1024 < port <= 65535 and not 18789 <= port <= 18799
            assert "--fresh" not in command
            ready = True
        elif command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(
                command, 0 if ready else 1, '{"phase":"Ready"}' if ready else "", "sandbox not found"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sid": "c" * 64})
    assert response.status_code == 200, response.text
    assert response.json()["sandbox_id"] == "p360-s-cccccccccccc"


def test_ready_sandbox_is_reused_when_nemoclaw_status_is_busy(adapter_http, monkeypatch):
    module, client = adapter_http
    commands = []

    def cli(command, **kwargs):
        commands.append(command)
        if command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(command, 0, '{"phase":"Ready"}', "")
        if command[1] == "onboard" or command[2] == "status":
            return subprocess.CompletedProcess(command, 1, "", "Failed to acquire portable-host.lock")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sid": "d" * 64})
    assert response.status_code == 200, response.text
    assert not any(command[1] == "onboard" for command in commands)


def test_unready_session_sandbox_is_replaced(adapter_http, monkeypatch):
    import json

    module, client = adapter_http
    phase = {"p360-s-cccccccccccc": "Error"}
    destroyed: list[str] = []
    onboarded: list[str] = []

    def cli(command, **kwargs):
        if command[1:3] == ["sandbox", "get"]:
            name = command[3]
            current = phase.get(name)
            if not current:
                return subprocess.CompletedProcess(command, 1, "", "sandbox not found")
            return subprocess.CompletedProcess(command, 0, json.dumps({"phase": current}), "")
        if command[1:3] == ["sandbox", "delete"]:
            destroyed.append(command[3])
            phase.pop(command[3], None)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "onboard":
            name = command[command.index("--name") + 1]
            onboarded.append(name)
            phase[name] = "Ready"
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sid": "c" * 64})
    assert response.status_code == 200, response.text
    assert response.json()["sandbox_id"] == "p360-s-cccccccccccc"
    assert destroyed == ["p360-s-cccccccccccc"]
    assert onboarded == ["p360-s-cccccccccccc"]


def test_failed_onboard_clears_an_unusable_leftover(adapter_http, monkeypatch):
    module, client = adapter_http
    destroyed: list[str] = []

    def cli(command, **kwargs):
        if command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(command, 1, "", "sandbox not found")
        if command[1:3] == ["sandbox", "delete"]:
            destroyed.append(command[3])
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "onboard":
            return subprocess.CompletedProcess(
                command, 1, "", "Onboarding exited before the step completed."
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sid": "g" * 64})
    assert response.status_code == 503
    assert destroyed == [
        "p360-s-gggggggggggg",
        "p360-s-ggggggggn1",
        "p360-s-ggggggggn2",
    ]
    assert "Onboarding exited before the step completed" in response.json()["detail"]


def test_ready_retry_name_is_reused_without_onboarding_the_poisoned_name(
    adapter_http, monkeypatch
):
    import json

    module, client = adapter_http
    onboarded: list[str] = []

    def cli(command, **kwargs):
        if command[1:3] == ["sandbox", "get"]:
            name = command[3]
            if name == "p360-s-de4ddd17n1":
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"phase": "Ready", "lifecycleGeneration": "g1"}), ""
                )
            return subprocess.CompletedProcess(command, 1, "", "sandbox not found")
        if command[1] == "onboard":
            onboarded.append(command[command.index("--name") + 1])
            return subprocess.CompletedProcess(command, 1, "", "should not onboard")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sandbox": "p360-s-de4ddd1725b2"})
    assert response.status_code == 200, response.text
    assert response.json()["sandbox_id"] == "p360-s-de4ddd17n1"
    assert onboarded == []


def test_poisoned_session_name_retries_with_a_new_box(adapter_http, monkeypatch):
    import json

    module, client = adapter_http
    ready: set[str] = set()
    onboarded: list[str] = []

    def cli(command, **kwargs):
        if command[1:3] == ["sandbox", "get"]:
            name = command[3]
            if name in ready:
                return subprocess.CompletedProcess(command, 0, json.dumps({"phase": "Ready"}), "")
            return subprocess.CompletedProcess(command, 1, "", "sandbox not found")
        if command[1:3] == ["sandbox", "delete"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "onboard":
            name = command[command.index("--name") + 1]
            onboarded.append(name)
            if name.endswith("n1"):
                ready.add(name)
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(
                command, 1, "", "Registry entry exists for leftover session"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sandbox": "p360-s-de4ddd1725b2"})
    assert response.status_code == 200, response.text
    assert response.json()["sandbox_id"] == "p360-s-de4ddd17n1"
    assert onboarded == ["p360-s-de4ddd1725b2", "p360-s-de4ddd17n1"]


def test_gateway_error_does_not_start_another_sandbox(adapter_http, monkeypatch):
    module, client = adapter_http
    commands = []

    def cli(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, "", "gateway connection refused")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post("/v1/sandboxes", json={"sid": "e" * 64})
    assert response.status_code == 503
    assert not any(command[1] == "onboard" for command in commands)


def test_new_session_does_not_collide_with_running_agent_cli(adapter_http, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    module, client = adapter_http
    host_fence = threading.Lock()
    agent_started = threading.Event()
    ready = False

    def cli(command, **kwargs):
        nonlocal ready
        if command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(
                command, 0 if ready else 1, '{"phase":"Ready"}' if ready else "", "sandbox not found"
            )
        if not host_fence.acquire(blocking=False):
            return subprocess.CompletedProcess(command, 1, "", "Failed to acquire portable-host.lock")
        try:
            if command[2] == "agent":
                agent_started.set()
                sleep(0.2)
                return subprocess.CompletedProcess(command, 0, '{"answer":"A completed answer."}', "")
            if command[1] == "onboard":
                ready = True
            return subprocess.CompletedProcess(command, 0, "", "")
        finally:
            host_fence.release()

    monkeypatch.setattr(module.subprocess, "run", cli)
    with ThreadPoolExecutor(max_workers=1) as workers:
        turn = workers.submit(
            client.post, "/v1/turns", json={"sandbox": "p360-s-abcdef123456", "input": "Summarize"}
        )
        assert agent_started.wait(timeout=2)
        startup = client.post("/v1/sandboxes", json={"sid": "f" * 64})
        assert turn.result().status_code == 200
    assert startup.status_code == 200, startup.text


def test_turn_logs_agent_elapsed(adapter_http, monkeypatch, capsys):
    import json

    module, client = adapter_http

    def cli(command, **kwargs):
        if len(command) > 2 and command[2] == "agent":
            return subprocess.CompletedProcess(command, 0, json.dumps({"answer": "Creatinine is 1.1 [obs_1]."}), "")
        raise AssertionError("Unexpected CLI operation")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post(
        "/v1/turns", json={"sandbox": "p360-s-abcdef123456", "patient_key": "p_101", "input": "Latest labs"}
    )
    assert response.status_code == 200, response.text
    out = capsys.readouterr().out
    assert "nemoclaw-turn: turn sandbox=p360-s-abcdef123456 session=ask-p360-s-abcdef123456" in out
    assert "agent=" in out
    assert "total=" in out


def test_unusable_turn_retries_on_a_fresh_agent_session(adapter_http, monkeypatch):
    import json

    module, client = adapter_http
    sessions: list[str] = []

    def cli(command, **kwargs):
        if len(command) > 2 and command[2] == "agent":
            sid = command[command.index("--session-id") + 1]
            sessions.append(sid)
            if "-1-" in sid:
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"answer": "Heart overlay is available [report_vista]."}), ""
                )
            return subprocess.CompletedProcess(
                command,
                1,
                json.dumps({"result": {"payloads": [{"text": "Agent couldn't generate a response. Please try again."}]}}),
                "incomplete_turn",
            )
        raise AssertionError("Unexpected CLI operation")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post(
        "/v1/turns",
        json={"sandbox": "p360-s-abcdef123456", "patient_key": "p_102", "input": "What overlays are possible?"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "Heart overlay is available [report_vista]."
    assert len(sessions) == 2
    assert sessions[0] != sessions[1]
    assert all(sid.startswith(module.agent_session_id("p360-s-abcdef123456")) for sid in sessions)


def test_turn_reuses_one_agent_session_per_sandbox(adapter_http, monkeypatch):
    import json

    module, client = adapter_http
    sessions = []

    def cli(command, **kwargs):
        if len(command) > 2 and command[2] == "agent":
            sessions.append(command[command.index("--session-id") + 1])
            return subprocess.CompletedProcess(command, 0, json.dumps({"answer": "Creatinine is 1.1 [obs_1]."}), "")
        raise AssertionError("Unexpected CLI operation")

    monkeypatch.setattr(module.subprocess, "run", cli)
    first = client.post(
        "/v1/turns", json={"sandbox": "p360-s-abcdef123456", "patient_key": "p_101", "input": "Latest labs"}
    )
    second = client.post(
        "/v1/turns", json={"sandbox": "p360-s-abcdef123456", "patient_key": "p_101", "input": "What about the dose?"}
    )
    other = client.post(
        "/v1/turns", json={"sandbox": "p360-s-ffffffffffff", "patient_key": "p_102", "input": "Latest labs"}
    )
    assert first.status_code == second.status_code == other.status_code == 200
    assert sessions[0].startswith(module.agent_session_id("p360-s-abcdef123456"))
    assert sessions[1].startswith(module.agent_session_id("p360-s-abcdef123456"))
    assert sessions[2].startswith(module.agent_session_id("p360-s-ffffffffffff"))
    assert sessions[0] != sessions[2]


def test_turn_asks_the_model_to_choose_lookups(adapter_http, monkeypatch):
    import json

    module, client = adapter_http
    agents = []

    def cli(command, **kwargs):
        if len(command) > 2 and command[2] == "exec":
            raise AssertionError("the host must not choose chart lookups")
        if len(command) > 2 and command[2] == "agent":
            agents.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps({"answer": "Pneumonia resolved."}), "")
        raise AssertionError("Unexpected CLI operation")

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.post(
        "/v1/turns",
        json={"sandbox": "p360-s-abcdef123456", "patient_key": "p_101", "input": "Summarize the latest note"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "Pneumonia resolved."
    assert len(agents) == 1
    assert agents[0][agents[0].index("--session-id") + 1].startswith(
        module.agent_session_id("p360-s-abcdef123456")
    )
    message = agents[0][agents[0].index("-m") + 1]
    assert "You decide which chart lookups" in message
    assert "allergies, diet" in message
    assert "imaging" in message
    assert "suppressed count" in message
    assert "availability" not in message
    assert "slots" not in message
    assert "Records:" not in message


def test_sandbox_status_reports_a_ready_generation_without_creating_one(adapter_http, monkeypatch):
    module, client = adapter_http
    seen = []

    def cli(command, **kwargs):
        seen.append(list(command))
        if command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(
                command, 0, '{"phase":"Ready","lifecycleGeneration":"gen-9"}', ""
            )
        raise AssertionError(command)

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.get("/v1/sandboxes/p360-s-abcdef123456")
    assert response.status_code == 200
    assert response.json() == {"ready": True, "generation": "gen-9"}
    assert all("onboard" not in part for command in seen for part in command)


def test_sandbox_status_accepts_openshell_created_at(adapter_http, monkeypatch):
    module, client = adapter_http

    def cli(command, **kwargs):
        if command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(
                command, 0, '{"phase":"Ready","created_at":"2026-09-22T02:05:00Z","id":"sb-1"}', ""
            )
        raise AssertionError(command)

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.get("/v1/sandboxes/p360-s-de4ddd17n1")
    assert response.status_code == 200
    assert response.json() == {"ready": True, "generation": "2026-09-22T02:05:00Z"}


def test_missing_sandbox_is_not_active(adapter_http, monkeypatch):
    module, client = adapter_http

    def cli(command, **kwargs):
        if command[1:3] == ["sandbox", "get"]:
            return subprocess.CompletedProcess(command, 1, "", "sandbox not found")
        raise AssertionError(command)

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.get("/v1/sandboxes/p360-s-abcdef123456")
    assert response.status_code == 200
    assert response.json() == {"ready": False}


def test_protected_sandbox_status_does_not_call_the_gateway(adapter_http, monkeypatch):
    module, client = adapter_http

    def cli(command, **kwargs):
        raise AssertionError(command)

    monkeypatch.setattr(module.subprocess, "run", cli)
    response = client.get("/v1/sandboxes/patient360")
    assert response.status_code == 200
    assert response.json() == {"ready": False}
