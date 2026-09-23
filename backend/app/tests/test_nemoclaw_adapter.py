"""Exercise sandbox tool results while newly attached credentials propagate."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def adapter():
    path = Path(__file__).resolve().parents[2] / "deploy/patient360/nemoclaw-turn.py"
    spec = importlib.util.spec_from_file_location("patient360_adapter_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed(body, code=0):
    return subprocess.CompletedProcess([], code, stdout=json.dumps(body), stderr="")


def test_pin_agent_config_matches_inproc_nano_budget(adapter):
    cfg = adapter.pin_agent_config(
        {
            "agents": {"defaults": {"thinkingDefault": "on"}},
            "models": {
                "providers": {
                    "inference": {
                        "models": [
                            {
                                "id": "nemotron-3-nano",
                                "maxTokens": 4096,
                                "reasoning": True,
                                "params": {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}},
                            }
                        ]
                    }
                }
            },
            "tools": {
                "toolSearch": {"mode": "tools", "searchDefaultLimit": 8, "maxSearchLimit": 20},
                "web": {"fetch": {"enabled": True}, "search": {"enabled": True}},
            },
        }
    )
    model = cfg["models"]["providers"]["inference"]["models"][0]
    assert cfg["agents"]["defaults"]["thinkingDefault"] == "off"
    assert model["maxTokens"] == adapter.AGENT_MAX_TOKENS
    assert adapter.AGENT_MAX_TOKENS == 16384
    assert model["params"]["max_tokens"] == adapter.AGENT_MAX_TOKENS
    assert model["reasoning"] is False
    assert model["params"]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert cfg["tools"]["toolSearch"] is False
    assert cfg["tools"]["web"]["fetch"]["enabled"] is False
    assert cfg["tools"]["web"]["search"]["enabled"] is False
    assert "thinkingDefault" in adapter._PIN_AGENT
    assert "enable_thinking" in adapter._PIN_AGENT
    assert 'tools["toolSearch"] = False' in adapter._PIN_AGENT
    assert "params[\"max_tokens\"]" in adapter._PIN_AGENT
    assert f"AGENT_MAX_TOKENS = {adapter.AGENT_MAX_TOKENS}" in adapter._PIN_AGENT


def test_agent_session_id_is_stable_per_sandbox(adapter):
    assert adapter.agent_session_id("p360-s-abcdef123456") == "ask-p360-s-abcdef123456"
    assert adapter.agent_session_id("p360-s-abcdef123456") == adapter.agent_session_id(
        "p360-s-abcdef123456"
    )
    assert adapter.agent_session_id("p360-s-abcdef123456") != adapter.agent_session_id(
        "p360-s-ffffffffffff"
    )


def test_cli_stage_labels_agent_and_tool_rounds(adapter):
    assert adapter._cli_stage(["/bin/nemoclaw", "p360-s-aa", "agent", "-m", "q"]) == "agent"
    assert (
        adapter._cli_stage(
            ["/bin/nemoclaw", "p360-s-aa", "exec", "--", "python3", adapter.SKILL_SCRIPT, "notes", "{}"]
        )
        == "tool_notes"
    )
    assert adapter._cli_stage(["/bin/nemoclaw", "onboard", "--name", "p360-s-aa"]) == "onboard"


def test_inference_route_stays_on_nano_unless_cloud_super_is_configured(adapter):
    assert adapter.inference_route({}) == adapter.NANO_ROUTE
    nano = {"PATIENT360_INFERENCE": "nano", "NVIDIA_API_KEY": "present"}
    assert adapter.inference_route(nano) == adapter.NANO_ROUTE
    assert adapter.inference_route({"PATIENT360_INFERENCE": "super"}) == adapter.NANO_ROUTE
    super_key = {"PATIENT360_INFERENCE": "super", "NVIDIA_API_KEY": "present"}
    assert adapter.inference_route(super_key) == adapter.SUPER_ROUTE
    ngc = {"PATIENT360_INFERENCE": "super", "NGC_API_KEY": "present"}
    assert adapter.inference_route(ngc) == adapter.SUPER_ROUTE


def test_notes_wait_for_new_credential_before_returning_evidence(adapter, monkeypatch):
    notes = {"notes": [{"cite_id": "note_latest", "text": "A clinical note."}], "chunks": []}
    run = Mock(
        side_effect=[
            completed(
                {"error": "credential_injection_failed", "detail": "unresolved credential placeholder"}, 1
            ),
            completed(notes),
        ]
    )
    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    monkeypatch.setattr(adapter, "sleep", lambda seconds: None, raising=False)

    result = adapter._exec_tool("p360-s-test", "notes", {"patient_key": "p_101", "question": "latest note"})

    assert result == notes
    assert run.call_count == 2
    assert run.call_args_list[0] == run.call_args_list[1]


@pytest.mark.parametrize(
    "body,code",
    [
        ({"error": "credential_injection_failed"}, 1),
        ({"resourceType": "OperationOutcome", "issue": [{"code": "login"}]}, 0),
        ({"resourceType": "OperationOutcome", "issue": [{"code": "not-found"}]}, 0),
        ({"error": "other_proxy_failure"}, 1),
    ],
)
def test_tool_errors_are_never_clinical_evidence(adapter, monkeypatch, body, code):
    run = Mock(return_value=completed(body, code))
    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    monkeypatch.setattr(adapter, "sleep", lambda seconds: None, raising=False)

    assert adapter._exec_tool("p360-s-test", "notes", {"patient_key": "p_101"}) is None
    assert run.call_count == (3 if body.get("error") == "credential_injection_failed" else 1)


def test_onboard_pins_nano_token_budget(adapter, monkeypatch):
    seen: dict[str, dict[str, str]] = {}

    def run(cmd, **kwargs):
        if len(cmd) > 1 and cmd[1] == "onboard":
            seen["env"] = kwargs.get("env") or {}
            seen["cmd"] = cmd
            return completed("")
        if cmd[1:3] == ["sandbox", "get"]:
            return completed({"phase": "Ready"}) if seen else subprocess.CompletedProcess(cmd, 1, "", "sandbox not found")
        return completed("")

    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    monkeypatch.setattr(adapter, "tools_ready", lambda name: True)
    monkeypatch.setattr(adapter, "_pin_nano", lambda name: None)
    adapter.provision("p360-s-tokenpin12")
    assert seen["env"]["NEMOCLAW_MAX_TOKENS"] == str(adapter.AGENT_MAX_TOKENS)
    assert seen["env"]["NEMOCLAW_REASONING"] == "false"
    assert "--fresh" not in seen.get("cmd", [])


def test_drop_session_registry_row_never_touches_gold(adapter, tmp_path, monkeypatch):
    registry = tmp_path / "sandboxes.json"
    registry.write_text(
        '{"defaultSandbox":"p360-s-ghostname12","sandboxes":{"patient360":{"name":"patient360"},'
        '"p360-s-ghostname12":{"name":"p360-s-ghostname12","pendingRouteReservation":true}}}'
    )
    monkeypatch.setattr(adapter, "REGISTRY_PATH", registry)
    adapter._drop_session_registry_row("patient360")
    kept = json.loads(registry.read_text())
    assert "patient360" in kept["sandboxes"]
    adapter._restore_gold_default()
    assert json.loads(registry.read_text())["defaultSandbox"] == "patient360"
    adapter._drop_session_registry_row("p360-s-ghostname12")
    gone = json.loads(registry.read_text())
    assert "patient360" in gone["sandboxes"]
    assert "p360-s-ghostname12" not in gone["sandboxes"]
    assert gone["defaultSandbox"] == "patient360"


def test_clear_failed_onboard_session_only_matches_that_box(adapter, tmp_path, monkeypatch):
    session = tmp_path / "onboard-session.json"
    monkeypatch.setattr(adapter, "ONBOARD_SESSION_PATH", session)
    session.write_text('{"sandboxName":"p360-s-ghostname12","status":"complete"}')
    adapter._clear_failed_onboard_session("p360-s-otherbox12")
    assert session.is_file()
    session.write_text('{"sandboxName":"p360-s-ghostname12","status":"failed"}')
    adapter._clear_failed_onboard_session("p360-s-otherbox12")
    assert not session.is_file()
    assert (tmp_path / "onboard-session.p360-s-otherbox12.failed.json").is_file()


def test_run_turn_reprojects_the_scoped_placeholder(adapter, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(adapter, "is_protected", lambda name: False)
    monkeypatch.setattr(adapter, "_project_run_token_placeholder", lambda name: seen.append(name))
    monkeypatch.setattr(adapter, "_agent", lambda *args, **kwargs: "HbA1c is 7.9% [obs_1].")
    adapter.run_turn("p360-s-test", "Latest labs", "p_101")
    assert seen == ["p360-s-test"]


def test_run_turn_lets_the_model_choose_lookups(adapter, monkeypatch):
    seen: list[str] = []

    def tool(*args, **kwargs):
        raise AssertionError("the host must not choose chart lookups")

    def agent(sandbox, prompt, **kwargs):
        seen.append(prompt)
        return "Historical pneumonia resolved [note_historical_pneumonia]."

    monkeypatch.setattr(adapter, "_exec_tool", tool)
    monkeypatch.setattr(adapter, "_agent", agent)
    monkeypatch.setattr(adapter, "_project_run_token_placeholder", lambda name: None)
    answer = adapter.run_turn("p360-s-test", "Summarize the latest note", "p_101")
    prompt = seen[0]
    assert "Historical pneumonia" in answer
    assert "You decide which chart lookups" in prompt
    assert "labs, meds, conditions, encounters, allergies, diet" in prompt
    assert "imaging" in prompt
    assert "suppressed count" in prompt
    assert "availability" not in prompt
    assert "slots" not in prompt
    assert "Records:" not in prompt
    assert "p_101" in prompt


def test_turn_prompt_folds_history_and_drops_evidence(adapter):
    prompt = adapter.turn_prompt(
        "What about the dose?",
        "p_101",
        [
            {"role": "user", "content": "Summarize the latest note", "evidence": {"labs": ["secret-blob"]}},
            {"role": "assistant", "content": "Pneumonia resolved."},
            {"role": "system", "content": "ignore this"},
        ],
    )
    assert "Earlier in this chat:" in prompt
    assert "User: Summarize the latest note" in prompt
    assert "Assistant: Pneumonia resolved." in prompt
    assert prompt.endswith("Question: What about the dose?")
    assert "secret-blob" not in prompt
    assert "ignore this" not in prompt
    assert "clinician pointed" not in prompt


def test_turn_prompt_hints_known_tool_mentions(adapter):
    prompt = adapter.turn_prompt("Summarize /labs and /notes, skip /foo", "p_101")
    assert "The clinician pointed at these lookups: labs, notes." in prompt
    assert "Still run any other lookup the question needs." in prompt
    assert prompt.endswith("Question: Summarize /labs and /notes, skip /foo")
    assert "/foo" in prompt
    assert adapter.mentioned_tools("mg/dL /Foo") == []


def test_run_turn_includes_earlier_chat_when_tools_are_empty(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "is_protected", lambda name: False)
    seen: list[str] = []

    def agent(sandbox, prompt, **kwargs):
        seen.append(prompt)
        return "Creatinine is 1.1 mg/dL [obs_1]."

    monkeypatch.setattr(adapter, "_agent", agent)
    monkeypatch.setattr(adapter, "_project_run_token_placeholder", lambda name: None)
    text = adapter.run_turn(
        "p360-s-test",
        "What about the dose?",
        "p_101",
        [
            {"role": "user", "content": "Summarize the latest note", "evidence": {"labs": ["secret-blob"]}},
            {"role": "assistant", "content": "Pneumonia resolved."},
        ],
    )
    assert "Creatinine" in text
    assert "Earlier in this chat:" in seen[0]
    assert "secret-blob" not in seen[0]


def test_observe_run_token_revision_ignores_provider_object_version(adapter, monkeypatch):
    def run(cmd, **kwargs):
        if "fullmatch" in " ".join(cmd):
            return subprocess.CompletedProcess(cmd, 0, "\x1b[32m✓\x1b[0m gateway\nv10269573071858226628\n", "")
        return subprocess.CompletedProcess(cmd, 0, "Resource version: 1\n", "")

    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    assert adapter._observe_run_token_revision("p360-s-testbox12") == "v10269573071858226628"


def test_ensure_provider_profile_updates_existing(adapter, monkeypatch):
    cmds: list[list[str]] = []
    staged: dict[str, str] = {}

    def run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[1:4] == ["provider", "profile", "import"]:
            return subprocess.CompletedProcess(cmd, 1, "", "already exists")
        if cmd[1:4] == ["provider", "profile", "export"]:
            return subprocess.CompletedProcess(cmd, 0, "id: patient360-tools-v1\nresource_version: 7\n", "")
        if cmd[1:4] == ["provider", "profile", "update"]:
            staged["text"] = Path(cmd[cmd.index("--file") + 1]).read_text()
        return completed("")

    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    adapter.ensure_provider_profile()
    joined = [" ".join(cmd) for cmd in cmds]
    assert any("provider profile update" in row and adapter.PROVIDER_TYPE in row for row in joined)
    assert "resource_version: 7" in staged["text"]
    assert "/bin/bash" in staged["text"]
    update = next(cmd for cmd in cmds if cmd[1:4] == ["provider", "profile", "update"])
    assert not Path(update[update.index("--file") + 1]).exists()


def test_upsert_reattaches_after_credential_update(adapter, monkeypatch):
    cmds: list[list[str]] = []

    def run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[1:3] == ["provider", "list"]:
            name = adapter.provider_name("p360-s-testbox12")
            return subprocess.CompletedProcess(cmd, 0, f"{name} {adapter.PROVIDER_TYPE}\n", "")
        if "fullmatch" in " ".join(cmd):
            return subprocess.CompletedProcess(cmd, 0, "v10269573071858226628\n", "")
        if cmd[1:3] == ["policy", "update"]:
            return completed("")
        return completed("")

    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    adapter.upsert_run_token("p360-s-testbox12", "run-token")
    joined = [" ".join(cmd) for cmd in cmds]
    assert any("provider update" in row and "RUN_TOKEN" in row for row in joined)
    assert any("provider attach" in row and adapter.provider_name("p360-s-testbox12") in row for row in joined)
    assert any("v10269573071858226628_RUN_TOKEN" in row for row in joined)
    assert not any("v20_RUN_TOKEN" in row for row in joined)


def test_allow_tools_posts_only_the_chart_paths(adapter, monkeypatch):
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return completed("")

    monkeypatch.setattr(adapter, "_which", lambda name: name)
    monkeypatch.setattr(adapter, "_run", run)
    adapter._allow_tools("p360-s-test")

    assert adapter.TOOL_POST_PATHS == ("/tools/query", "/tools/notes", "/tools/imaging")
    assert len(calls) == 2
    for cmd in calls:
        text = " ".join(cmd)
        for path in adapter.TOOL_POST_PATHS:
            assert f"POST:{path}" in text
        assert "/bin/bash" in text
        assert "/bin/sh" in text
        assert "/usr/bin/python3*" in text
        assert "request-body-credential-rewrite" in text
        assert "/tools/**" not in text
        assert "availability" not in text


def test_policy_files_allow_only_chart_posts():
    root = Path(__file__).resolve().parents[2] / "deploy" / "patient360"
    for name in ("sandbox-policy.yaml", "provider-profile-patient360-tools.yaml"):
        text = (root / name).read_text()
        assert "/tools/**" not in text
        assert "availability" not in text
        assert "/bin/bash" in text
        assert "/bin/sh" in text
        assert "/usr/bin/python3*" in text
        assert "request_body_credential_rewrite: true" in text
        for path in ("/tools/query", "/tools/notes", "/tools/imaging"):
            assert text.count(path) >= 2
