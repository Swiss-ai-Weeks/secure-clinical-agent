"""The sandbox skill script posts only the chart tools the PDP already checks."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def tools():
    path = (
        Path(__file__).resolve().parents[2]
        / "deploy/patient360/skills/patient360-tools/p360_tools.py"
    )
    spec = importlib.util.spec_from_file_location("patient360_tools_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_authorization_prefers_the_refreshed_file_over_a_stale_env(tools, tmp_path, monkeypatch):
    ref = tmp_path / ".run_token_ref"
    ref.write_text("openshell:resolve:env:v10269573071858226628_RUN_TOKEN\n")
    monkeypatch.setattr(tools, "PLACEHOLDER_FILE", str(ref))
    monkeypatch.setenv("RUN_TOKEN", "openshell:resolve:env:v21_RUN_TOKEN")
    assert tools.authorization() == "Bearer openshell:resolve:env:v10269573071858226628_RUN_TOKEN"
    ref.write_text("openshell:resolve:env:RUN_TOKEN\n")
    assert tools.authorization() == "Bearer openshell:resolve:env:v21_RUN_TOKEN"


def test_imaging_posts_to_the_imaging_tool(tools, monkeypatch):
    seen: dict[str, object] = {}

    def post_tool(url, body, timeout):
        seen["url"] = url
        seen["body"] = body
        seen["timeout"] = timeout
        return 200, '{"studies":[]}'

    monkeypatch.setattr(tools, "post_tool", post_tool)
    monkeypatch.setattr(tools.sys, "argv", ["p360_tools.py", "imaging", '{"patient_key":"p_101"}'])

    assert tools.main() == 0
    assert str(seen["url"]).endswith("/tools/imaging")
    assert seen["body"]["patient_key"] == "p_101"
    assert seen["timeout"] == 30


def test_imaging_classes_use_a_long_timeout(tools, monkeypatch):
    seen: dict[str, object] = {}

    def post_tool(url, body, timeout):
        seen["timeout"] = timeout
        seen["body"] = body
        return 200, '{"overlay_text":"heart"}'

    monkeypatch.setattr(tools, "post_tool", post_tool)
    monkeypatch.setattr(
        tools.sys,
        "argv",
        ["p360_tools.py", "imaging", '{"patient_key":"p_102","classes":["heart"]}'],
    )

    assert tools.main() == 0
    assert seen["timeout"] == 300
    assert seen["body"]["classes"] == ["heart"]


def test_imaging_retries_unresolved_credentials(tools, monkeypatch):
    calls = {"n": 0}

    def post_tool(url, body, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return 502, '{"error":"credential_injection_failed","detail":"unresolved"}'
        return 200, '{"studies":[]}'

    monkeypatch.setattr(tools, "post_tool", post_tool)
    monkeypatch.setattr(tools.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(tools.sys, "argv", ["p360_tools.py", "imaging", '{"patient_key":"p_101"}'])

    assert tools.main() == 0
    assert calls["n"] == 2


def test_post_tool_uses_curl_and_puts_placeholder_in_the_body(tools, monkeypatch, tmp_path):
    ref = tmp_path / ".run_token_ref"
    ref.write_text("openshell:resolve:env:v9_RUN_TOKEN\n")
    monkeypatch.setattr(tools, "PLACEHOLDER_FILE", str(ref))
    monkeypatch.delenv("RUN_TOKEN", raising=False)
    seen: list[list[str]] = []

    def run(cmd, **kwargs):
        seen.append(cmd)
        return type("P", (), {"returncode": 0, "stdout": '{"notes":[]}\nHTTP_STATUS:200', "stderr": ""})()

    monkeypatch.setattr(tools.subprocess, "run", run)
    code, raw = tools.post_tool("http://host.openshell.internal:8088/tools/notes", {"patient_key": "p_101"}, 30)
    assert code == 200
    assert raw.startswith('{"notes":[]}')
    cmd = seen[0]
    assert cmd[0] == "/usr/bin/curl"
    assert "Authorization: Bearer openshell:resolve:env:v9_RUN_TOKEN" in cmd
    body = json.loads(cmd[cmd.index("-d") + 1])
    assert body["openshell_resolve"] == "openshell:resolve:env:v9_RUN_TOKEN"
    assert body["patient_key"] == "p_101"


def test_unknown_verb_is_rejected(tools, monkeypatch):
    monkeypatch.setattr(tools.sys, "argv", ["p360_tools.py", "availability", "{}"])

    def post_tool(url, body, timeout):
        raise AssertionError("an unknown verb must not call the network")

    monkeypatch.setattr(tools, "post_tool", post_tool)
    assert tools.main() == 2
