#!/usr/bin/env python3
"""Host adapter: per-session NemoClaw sandboxes and RUN_TOKEN provider updates.

The backend container cannot use the NemoClaw CLI (HOME, mTLS client files).
Bind on the Patient360 docker-bridge gateway so the backend can reach us.
The gold sandbox `patient360` is never the Ask runtime.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter, sleep
from typing import Any
from urllib.parse import unquote

GOLD = "patient360"
AGENT = os.environ.get("PATIENT360_OPENSHELL_AGENT", "main")
HOST = os.environ.get("PATIENT360_NEMOCLAW_TURN_HOST", "0.0.0.0")
PORT = int(os.environ.get("PATIENT360_NEMOCLAW_TURN_PORT", "17999"))
TIMEOUT = int(os.environ.get("PATIENT360_NEMOCLAW_TURN_TIMEOUT", "180"))
ONBOARD_TIMEOUT = int(os.environ.get("PATIENT360_SANDBOX_ONBOARD_TIMEOUT", "600"))
TOOLS_URL = os.environ.get("PATIENT360_TOOLS_URL", "http://host.openshell.internal:8088")
HERE = Path(__file__).resolve().parent
POLICY = HERE / "sandbox-policy.yaml"
SKILL = HERE / "skills" / "patient360-tools"
SKILL_SCRIPT = "/sandbox/.openclaw/workspace/skills/patient360-tools/p360_tools.py"
PROVIDER_PROFILE = HERE / "provider-profile-patient360-tools.yaml"
PROVIDER_TYPE = "patient360-tools-v1"
SESSION_PREFIX = "p360-s-"
DESTROY_PREFIXES = (SESSION_PREFIX, "p360-pool-", "p360-probe-")
REGISTRY_PATH = Path.home() / ".nemoclaw" / "sandboxes.json"
ONBOARD_SESSION_PATH = Path.home() / ".nemoclaw" / "onboard-session.json"
TOOL_POST_PATHS = ("/tools/query", "/tools/notes", "/tools/imaging")
AGENT_MAX_TOKENS = 16384

_locks: dict[str, threading.Lock] = {}
_locks_mu = threading.Lock()
# NemoClaw onboarding owns shared recovery state, even for different sandboxes.
_onboard_mu = threading.Lock()
# CLI lifecycle/agent commands also share NemoClaw's portable host fence.
_nemoclaw_mu = threading.Lock()
_tuning_ready: set[str] = set()
_turn_stages = threading.local()


def _lock(name: str) -> threading.Lock:
    with _locks_mu:
        return _locks.setdefault(name, threading.Lock())


def agent_session_id(sandbox: str) -> str:
    """One OpenClaw session per Ask thread. The sandbox is already per login."""
    return f"ask-{sandbox}"


def pin_agent_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Thinking off. Tool-using Ask turns hit stop=length at 800 and 2048."""
    agents = cfg.setdefault("agents", {})
    if not isinstance(agents, dict):
        agents = {}
        cfg["agents"] = agents
    defaults = agents.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
        agents["defaults"] = defaults
    defaults["thinkingDefault"] = "off"
    models = cfg.get("models")
    providers = models.get("providers") if isinstance(models, dict) else None
    if isinstance(providers, dict):
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            rows = provider.get("models")
            if not isinstance(rows, list):
                continue
            for model in rows:
                if not isinstance(model, dict):
                    continue
                model["maxTokens"] = AGENT_MAX_TOKENS
                model["reasoning"] = False
                params = model.get("params")
                if not isinstance(params, dict):
                    params = {}
                    model["params"] = params
                params["max_tokens"] = AGENT_MAX_TOKENS
                extra = params.get("extra_body")
                if not isinstance(extra, dict):
                    extra = {}
                    params["extra_body"] = extra
                kwargs = extra.get("chat_template_kwargs")
                if not isinstance(kwargs, dict):
                    kwargs = {}
                    extra["chat_template_kwargs"] = kwargs
                kwargs["enable_thinking"] = False
    tools = cfg.setdefault("tools", {})
    if not isinstance(tools, dict):
        tools = {}
        cfg["tools"] = tools
    # Keep exec/read/write visible. toolSearch mode "tools" only exposes
    # tool_search/tool_describe/tool_call, and search returns no chart skill.
    tools["toolSearch"] = False
    web = tools.setdefault("web", {})
    if not isinstance(web, dict):
        web = {}
        tools["web"] = web
    web.setdefault("fetch", {})["enabled"] = False
    web.setdefault("search", {})["enabled"] = False
    return cfg


def _cli_stage(cmd: list[str]) -> str:
    if len(cmd) > 2 and cmd[2] == "agent":
        return "agent"
    if len(cmd) > 1 and cmd[1] == "onboard":
        return "onboard"
    if SKILL_SCRIPT in cmd:
        idx = cmd.index(SKILL_SCRIPT)
        kind = cmd[idx + 1] if idx + 1 < len(cmd) else ""
        if kind in {"notes", "query", "imaging"}:
            return f"tool_{kind}"
    if len(cmd) > 2 and cmd[2] == "exec":
        joined = " ".join(cmd)
        if "openclaw.json" in joined or "thinkingDefault" in joined:
            return "pin_latency"
        return "exec"
    return Path(cmd[0]).name


def _record_stage(label: str, seconds: float) -> None:
    items = getattr(_turn_stages, "items", None)
    if isinstance(items, list):
        items.append((label, seconds))
    print(f"nemoclaw-turn: {label} elapsed={seconds:.2f}s", flush=True)


def _format_stages(items: list[tuple[str, float]] | None) -> str:
    if not items:
        return ""
    return " ".join(f"{name}={seconds:.2f}s" for name, seconds in items)


def _which(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    home = Path.home() / ".local" / "bin" / name
    if home.is_file():
        return str(home)
    raise RuntimeError(f"{name} not on PATH")


def _env() -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{Path.home() / '.local' / 'bin'}:{os.environ.get('PATH', '')}",
        "NEMOCLAW_NON_INTERACTIVE": "1",
    }


def _run(
    cmd: list[str], *, timeout: int, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    guard = _nemoclaw_mu if Path(cmd[0]).name == "nemoclaw" else nullcontext()
    started = perf_counter()
    try:
        with guard:
            return subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=env or _env(),
            )
    finally:
        label = _cli_stage(cmd)
        if label in {"agent", "onboard", "pin_latency"} or label.startswith("tool_"):
            _record_stage(label, perf_counter() - started)


def session_sandbox_name(sid: str) -> str:
    token = "".join(ch for ch in sid.lower() if ch.isalnum())[:12]
    if len(token) < 8:
        raise ValueError("sid too short")
    return f"{SESSION_PREFIX}{token}"


def _next_session_names(name: str) -> list[str]:
    """Fresh Ask box names when the sid-derived name is poisoned in NemoClaw."""
    if is_protected(name):
        return []
    token = "".join(ch for ch in name[len(SESSION_PREFIX) :] if ch.isalnum())[:8]
    alts: list[str] = []
    for attempt in (1, 2):
        alt = f"{SESSION_PREFIX}{token}n{attempt}"
        if alt != name and not is_protected(alt):
            alts.append(alt)
    return alts


def is_protected(name: str) -> bool:
    return name == GOLD or not name.startswith(DESTROY_PREFIXES)


def provider_name(sandbox: str) -> str:
    return f"{sandbox}-tools"


def _agent_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        for item in payload:
            text = _agent_text(item)
            if text:
                return text
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in (
        "finalAssistantVisibleText",
        "finalAssistantRawText",
        "answer",
        "output",
        "text",
        "message",
        "payloads",
        "result",
        "meta",
    ):
        if key in payload:
            text = _agent_text(payload[key])
            if text:
                return text
    return ""


def sandbox_liveness(name: str) -> dict:
    """Ready session sandboxes report a generation. This never creates a sandbox."""
    if is_protected(name):
        return {"ready": False}
    proc = _run([_which("openshell"), "sandbox", "get", name, "-o", "json"], timeout=30)
    if proc.returncode != 0:
        return {"ready": False}
    try:
        state = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ready": False}
    if not isinstance(state, dict) or state.get("phase") != "Ready":
        return {"ready": False}
    generation = str(
        state.get("lifecycleGeneration")
        or state.get("createdAt")
        or state.get("created_at")
        or state.get("id")
        or ""
    ).strip()
    if not generation:
        return {"ready": False}
    return {"ready": True, "generation": generation}


def sandbox_ready(name: str) -> bool:
    if is_protected(name):
        return False
    # NemoClaw status performs host-wide lifecycle work and can fail while a
    # different session is onboarding. Ask the gateway for actual existence.
    proc = _run([_which("openshell"), "sandbox", "get", name, "-o", "json"], timeout=30)
    if proc.returncode != 0:
        if "sandbox not found" in (proc.stderr or "").lower():
            return False
        raise RuntimeError("Cannot check sandbox readiness: gateway request failed")
    state = json.loads(proc.stdout)
    if state.get("phase") != "Ready":
        raise RuntimeError("Session sandbox exists but is not ready")
    return True


NANO_ROUTE = ("vllm-local", "nvidia/nemotron-3-nano")
SUPER_ROUTE = ("nvidia-prod", "nvidia/nemotron-3-super-120b-a12b")


def inference_route(env: dict[str, str] | None = None) -> tuple[str, str]:
    """inference.local stays on Nano unless PATIENT360_INFERENCE=super and a cloud key is set.

    A missing cloud credential does not start local Super. The gateway keeps Nano.
    """
    values = os.environ if env is None else env
    mode = str(values.get("PATIENT360_INFERENCE") or "nano").strip().lower()
    if mode != "super":
        return NANO_ROUTE
    if not str(values.get("NVIDIA_API_KEY") or "").strip() and not str(values.get("NGC_API_KEY") or "").strip():
        return NANO_ROUTE
    return SUPER_ROUTE


def _pin_nano(name: str) -> None:
    """Pin this sandbox's inference.local route. Default is local Nano."""
    provider, model = inference_route()
    proc = _run(
        [
            _which("nemoclaw"),
            "inference",
            "set",
            "--provider",
            provider,
            "--model",
            model,
            "--sandbox",
            name,
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "inference set failed").strip()
        raise RuntimeError(err[:300])


def _policy_document(name: str) -> str:
    proc = _run([_which("openshell"), "policy", "get", "--base", name], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "policy get failed").strip()[:300])
    text = proc.stdout or ""
    marker = "\n---\n"
    return text.split(marker, 1)[1] if marker in text else text


def _bind_run_token_policy(name: str) -> None:
    """Attach this sandbox's generic provider to /tools/* so RUN_TOKEN rewrites."""
    import tempfile

    import yaml

    raw = _policy_document(name)
    policy = yaml.safe_load(raw) or {}
    provider = provider_name(name)
    changed = False
    for entry in (policy.get("network_policies") or {}).values():
        if not isinstance(entry, dict):
            continue
        for endpoint in entry.get("endpoints") or []:
            if not isinstance(endpoint, dict):
                continue
            if endpoint.get("host") != "host.openshell.internal":
                continue
            if endpoint.get("port") not in (8088, 8080):
                continue
            if endpoint.get("protocol") not in (None, "rest"):
                continue
            binding = endpoint.get("credential_binding")
            if not isinstance(binding, dict) or binding.get("provider") != provider:
                endpoint["credential_binding"] = {"provider": provider}
                changed = True
    if not changed:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        yaml.safe_dump(policy, handle, sort_keys=False)
        path = handle.name
    try:
        os.chmod(path, 0o600)
        proc = _run(
            [_which("openshell"), "policy", "set", "--policy", path, "--wait", name],
            timeout=90,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "policy set failed").strip()
            raise RuntimeError(err[:300])
    finally:
        Path(path).unlink(missing_ok=True)


PLACEHOLDER_FILE = "/sandbox/.openclaw/workspace/skills/patient360-tools/.run_token_ref"


_REVISION = re.compile(r"^(v[0-9]{1,20}|s[a-f0-9]{64})$")
_OBSERVE_REVISION = (
    "import os, re, sys\n"
    "value = os.environ.get('RUN_TOKEN') or ''\n"
    "match = re.fullmatch(r'openshell:resolve:env:(v[0-9]{1,20}|s[a-f0-9]{64})_RUN_TOKEN', value)\n"
    "if not match:\n"
    "    sys.exit(1)\n"
    "print(match.group(1))\n"
)


def _observe_run_token_revision(name: str) -> str | None:
    """Revision OpenShell injects into a fresh exec. Provider resource version is a different counter."""
    proc = _run(
        [_which("nemoclaw"), name, "exec", "--no-tty", "--", "python3", "-c", _OBSERVE_REVISION],
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    for line in reversed((proc.stdout or "").splitlines()):
        token = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if _REVISION.fullmatch(token):
            return token
    return None


def _project_run_token_placeholder(name: str) -> None:
    """Copy the live exec revision into the file the in-sandbox agent reads."""
    revision = _observe_run_token_revision(name)
    if not revision:
        print(f"nemoclaw-turn: no live RUN_TOKEN revision for {name}", flush=True)
        return
    placeholder = f"openshell:resolve:env:{revision}_RUN_TOKEN"
    script = (
        "import pathlib\n"
        f"pathlib.Path({PLACEHOLDER_FILE!r}).write_text({placeholder!r} + chr(10))\n"
    )
    proc = _run(
        [_which("nemoclaw"), name, "exec", "--no-tty", "--", "python3", "-c", script],
        timeout=30,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "placeholder write failed").strip()
        print(f"nemoclaw-turn: placeholder project skipped on {name}: {err[:200]}", flush=True)
        return
    print(f"nemoclaw-turn: projected {placeholder} on {name}", flush=True)


def tools_ready(name: str) -> bool:
    skill = _run(
        [_which("nemoclaw"), name, "exec", "--no-tty", "--", "test", "-f", SKILL_SCRIPT],
        timeout=30,
    )
    return skill.returncode == 0


def _skill_current(name: str) -> bool:
    """True when the installed script prefers the refreshed placeholder file."""
    script = (
        "import pathlib, sys\n"
        f"path = pathlib.Path({SKILL_SCRIPT!r})\n"
        "text = path.read_text() if path.is_file() else ''\n"
        "sys.exit(0 if 'P360_PLACEHOLDER_SOURCE = \"file\"' in text else 1)\n"
    )
    proc = _run(
        [_which("nemoclaw"), name, "exec", "--no-tty", "--", "python3", "-c", script],
        timeout=30,
    )
    return proc.returncode == 0


def _ensure_skill(name: str) -> None:
    if tools_ready(name) and _skill_current(name):
        _ensure_agent_tuning(name)
        return
    _harden(name)


def provider_type(name: str) -> str:
    proc = _run([_which("openshell"), "provider", "list"], timeout=20)
    blob = proc.stdout or ""
    for line in blob.splitlines():
        parts = line.split()
        if parts and parts[0] == name:
            return parts[1] if len(parts) > 1 else ""
    return ""


def _allow_tools(name: str) -> None:
    """Permit query, notes, and imaging on the OpenShell host hop. One endpoint per update."""
    openshell = _which("openshell")
    binaries = [
        "--binary",
        "/usr/bin/curl",
        "--binary",
        "/usr/bin/python3",
        "--binary",
        "/usr/bin/python3*",
        "--binary",
        "/bin/bash",
        "--binary",
        "/usr/bin/bash",
        "--binary",
        "/bin/sh",
        "--binary",
        "/usr/bin/sh",
        "--binary",
        "/usr/local/bin/openclaw",
        "--binary",
        "/usr/local/bin/node",
        "--binary",
        "/usr/bin/node",
    ]
    for port, rule in (("8088", "patient360-tools"), ("8080", "patient360-tools-8080")):
        allows: list[str] = []
        for path in TOOL_POST_PATHS:
            allows.extend(["--add-allow", f"host.openshell.internal:{port}:POST:{path}"])
        allows.extend(["--add-allow", f"host.openshell.internal:{port}:GET:/healthz"])
        _run(
            [
                openshell,
                "policy",
                "update",
                name,
                "--wait",
                "--rule-name",
                rule,
                "--add-endpoint",
                f"host.openshell.internal:{port}:read-write:rest:enforce:request-body-credential-rewrite,allowed-ip=10.0.0.0/8,allowed-ip=172.16.0.0/12,allowed-ip=192.168.0.0/16",
                *binaries,
                *allows,
            ],
            timeout=60,
        )


_PIN_AGENT = (
    "import json, pathlib\n"
    f"AGENT_MAX_TOKENS = {AGENT_MAX_TOKENS}\n"
    """
def pin_agent_config(cfg):
    agents = cfg.setdefault("agents", {})
    if not isinstance(agents, dict):
        agents = {}
        cfg["agents"] = agents
    defaults = agents.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
        agents["defaults"] = defaults
    defaults["thinkingDefault"] = "off"
    models = cfg.get("models")
    providers = models.get("providers") if isinstance(models, dict) else None
    if isinstance(providers, dict):
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            rows = provider.get("models")
            if not isinstance(rows, list):
                continue
            for model in rows:
                if not isinstance(model, dict):
                    continue
                model["maxTokens"] = AGENT_MAX_TOKENS
                model["reasoning"] = False
                params = model.get("params")
                if not isinstance(params, dict):
                    params = {}
                    model["params"] = params
                params["max_tokens"] = AGENT_MAX_TOKENS
                extra = params.get("extra_body")
                if not isinstance(extra, dict):
                    extra = {}
                    params["extra_body"] = extra
                kwargs = extra.get("chat_template_kwargs")
                if not isinstance(kwargs, dict):
                    kwargs = {}
                    extra["chat_template_kwargs"] = kwargs
                kwargs["enable_thinking"] = False
    tools = cfg.setdefault("tools", {})
    if not isinstance(tools, dict):
        tools = {}
        cfg["tools"] = tools
    tools["toolSearch"] = False
    web = tools.setdefault("web", {})
    if not isinstance(web, dict):
        web = {}
        tools["web"] = web
    web.setdefault("fetch", {})["enabled"] = False
    web.setdefault("search", {})["enabled"] = False
    return cfg
p = pathlib.Path("/sandbox/.openclaw/openclaw.json")
p.write_text(json.dumps(pin_agent_config(json.loads(p.read_text())), indent=2) + "\\n")
"""
)


def _pin_agent_tuning(name: str) -> None:
    """Write thinking-off and the completion cap into this sandbox's OpenClaw config."""
    proc = _run(
        [_which("nemoclaw"), name, "exec", "--no-tty", "--", "python3", "-c", _PIN_AGENT],
        timeout=30,
    )
    if proc.returncode == 0:
        _tuning_ready.add(name)
        return
    print(f"nemoclaw-turn: latency pin skipped on {name}", flush=True)


def _ensure_agent_tuning(name: str) -> None:
    if name in _tuning_ready:
        return
    _pin_agent_tuning(name)


def _harden(name: str) -> None:
    _allow_tools(name)
    if SKILL.is_dir():
        _run([_which("nemoclaw"), name, "skill", "install", str(SKILL)], timeout=60)
    _pin_agent_tuning(name)


def _restore_gold_default() -> None:
    """Session onboard must not steal NemoClaw's default away from gold."""
    if not REGISTRY_PATH.is_file():
        return
    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except json.JSONDecodeError:
        return
    boxes = data.get("sandboxes")
    if not isinstance(boxes, dict) or GOLD not in boxes:
        return
    if data.get("defaultSandbox") == GOLD:
        return
    data["defaultSandbox"] = GOLD
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, REGISTRY_PATH)
    print("nemoclaw-turn: restored gold as default sandbox", flush=True)


def _drop_session_registry_row(name: str) -> None:
    """Remove a session row from the local NemoClaw registry. Never the gold box.

    `nemoclaw destroy` on a leftover session name resolves a missing dashboard
    port to 18789 (the gold box) and then refuses to drop the row.
    """
    if is_protected(name) or not REGISTRY_PATH.is_file():
        return
    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except json.JSONDecodeError:
        return
    boxes = data.get("sandboxes")
    if not isinstance(boxes, dict) or name not in boxes or GOLD not in boxes:
        return
    boxes.pop(name, None)
    if data.get("defaultSandbox") == name:
        data["defaultSandbox"] = GOLD
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, REGISTRY_PATH)
    print(f"nemoclaw-turn: dropped registry row {name}", flush=True)


def _clear_failed_onboard_session(name: str) -> None:
    """Do not resume a leftover onboard session. Ask always creates."""
    if is_protected(name) or not ONBOARD_SESSION_PATH.is_file():
        return
    try:
        body = json.loads(ONBOARD_SESSION_PATH.read_text())
    except json.JSONDecodeError:
        return
    session_name = str(body.get("sandboxName") or "")
    status = str(body.get("status") or "")
    if session_name != name and status not in {"failed"}:
        return
    dest = ONBOARD_SESSION_PATH.with_name(f"onboard-session.{name}.failed.json")
    os.replace(ONBOARD_SESSION_PATH, dest)
    print(f"nemoclaw-turn: cleared onboard session before {name}", flush=True)


def _destroy_unlocked(name: str) -> None:
    """Drop a session box. Caller must already hold _lock(name). Never the gold box."""
    if is_protected(name):
        raise RuntimeError("refusing to destroy gold or unknown sandbox")
    _tuning_ready.discard(name)
    dropped = _run([_which("openshell"), "sandbox", "delete", name], timeout=60)
    if dropped.returncode != 0:
        err = (dropped.stderr or dropped.stdout or "").strip()
        if "not found" not in err.lower():
            print(f"nemoclaw-turn: openshell delete {name} failed: {err[:200]}", flush=True)
    _drop_session_registry_row(name)
    _run([_which("openshell"), "provider", "delete", provider_name(name)], timeout=20)


def _onboard_session(name: str) -> None:
    """Create one session box. Caller holds _onboard_mu and _lock(name)."""
    if is_protected(name):
        raise RuntimeError("refusing gold or unknown sandbox name")
    _drop_session_registry_row(name)
    _clear_failed_onboard_session(name)
    # The CLI's default dashboard pool holds only eleven sessions.
    # Ask does not need a fixed dashboard URL. Let the OS select a free
    # host port; onboarding validates/reserves it before starting.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        dashboard_port = listener.getsockname()[1]
    env = _env()
    env["NEMOCLAW_PROVIDER"] = "vllm"
    env["NEMOCLAW_MODEL"] = "nvidia/nemotron-3-nano"
    env["NEMOCLAW_MAX_TOKENS"] = str(AGENT_MAX_TOKENS)
    env["NEMOCLAW_REASONING"] = "false"
    proc = _run(
        [
            _which("nemoclaw"),
            "onboard",
            "--name",
            name,
            "--agent",
            "openclaw",
            "--control-ui-port",
            str(dashboard_port),
            "--non-interactive",
            "--yes",
            "--no-gpu",
            "--no-sandbox-gpu",
            "--no-observability",
            "--yes-i-accept-third-party-software",
        ],
        timeout=ONBOARD_TIMEOUT,
        env=env,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "onboard failed").strip()
        print(f"nemoclaw-turn: onboard {name} failed: {err[:400]}", flush=True)
        try:
            ready = sandbox_ready(name)
        except RuntimeError:
            ready = False
        if not ready:
            _destroy_unlocked(name)
            raise RuntimeError(err[:400])
        print(
            f"nemoclaw-turn: onboard exited {proc.returncode} but {name} is Ready",
            flush=True,
        )
    try:
        _pin_nano(name)
    except RuntimeError as exc:
        print(f"nemoclaw-turn: pin skipped on {name}: {exc}", flush=True)
    _restore_gold_default()
    if not sandbox_ready(name):
        raise RuntimeError("sandbox not ready after onboard")
    _ensure_skill(name)


def _usable_session_sandbox(name: str) -> bool:
    """Ready and reusable. Missing is False. Unusable leftovers are removed."""
    try:
        return sandbox_ready(name)
    except RuntimeError as exc:
        if "not ready" not in str(exc).lower():
            raise
        print(f"nemoclaw-turn: replacing unusable sandbox {name}", flush=True)
        _destroy_unlocked(name)
        return False


def provision(name: str) -> str:
    if is_protected(name):
        raise RuntimeError("refusing gold or unknown sandbox name")
    with _lock(name):
        if _usable_session_sandbox(name):
            _ensure_skill(name)
            return name
        for alt in _next_session_names(name):
            if sandbox_liveness(alt).get("ready"):
                with _lock(alt):
                    if _usable_session_sandbox(alt):
                        _ensure_skill(alt)
                        return alt
        with _onboard_mu:
            try:
                _onboard_session(name)
                return name
            except RuntimeError as exc:
                last = exc
                for alt in _next_session_names(name):
                    print(f"nemoclaw-turn: retrying onboard as {alt}: {last}", flush=True)
                    with _lock(alt):
                        try:
                            if _usable_session_sandbox(alt):
                                _ensure_skill(alt)
                                return alt
                            _onboard_session(alt)
                            return alt
                        except RuntimeError as retry_exc:
                            last = retry_exc
                raise last


def _profile_resource_version(blob: str) -> str | None:
    text = re.sub(r"\x1b\[[0-9;]*m", "", blob or "")
    match = re.search(r"^resource_version:\s*(\d+)\s*$", text, re.M)
    return match.group(1) if match else None


def _stage_provider_profile(version: str) -> Path:
    text = PROVIDER_PROFILE.read_text()
    if re.search(r"^resource_version:", text, re.M):
        text = re.sub(
            r"^resource_version:\s*\d+\s*$",
            f"resource_version: {version}",
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = re.sub(r"^(id:\s+\S+\s*)$", rf"\1\nresource_version: {version}", text, count=1, flags=re.M)
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    handle.write(text)
    handle.close()
    return Path(handle.name)


def ensure_provider_profile() -> None:
    if not PROVIDER_PROFILE.is_file():
        raise RuntimeError("missing Patient360 OpenShell provider profile")
    openshell = _which("openshell")
    imported = _run(
        [openshell, "provider", "profile", "import", "--file", str(PROVIDER_PROFILE)],
        timeout=30,
    )
    if imported.returncode == 0:
        return
    exported = _run([openshell, "provider", "profile", "export", PROVIDER_TYPE], timeout=20)
    version = _profile_resource_version(exported.stdout or "")
    staged: Path | None = None
    try:
        if exported.returncode == 0 and version:
            staged = _stage_provider_profile(version)
            updated = _run(
                [
                    openshell,
                    "provider",
                    "profile",
                    "update",
                    "--file",
                    str(staged),
                    PROVIDER_TYPE,
                ],
                timeout=30,
            )
            if updated.returncode == 0:
                print(f"nemoclaw-turn: updated provider profile {PROVIDER_TYPE} v{version}", flush=True)
                return
            err = (updated.stderr or imported.stderr or imported.stdout or "profile update failed").strip()
        else:
            err = (imported.stderr or imported.stdout or "profile import failed").strip()
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    if exported.returncode != 0:
        raise RuntimeError(err[:300])
    print(f"nemoclaw-turn: profile update skipped: {err[:160]}", flush=True)


def upsert_run_token(sandbox: str, token: str) -> None:
    if is_protected(sandbox):
        raise RuntimeError("refusing credentials on gold sandbox")
    ensure_provider_profile()
    env = _env()
    env["RUN_TOKEN"] = token
    prov = provider_name(sandbox)
    openshell = _which("openshell")
    if provider_type(prov) != PROVIDER_TYPE:
        _run([openshell, "provider", "delete", prov], timeout=20)
        created = _run(
            [
                openshell,
                "provider",
                "create",
                "--name",
                prov,
                "--type",
                PROVIDER_TYPE,
                "--credential",
                "RUN_TOKEN",
            ],
            timeout=20,
            env=env,
        )
        if created.returncode != 0:
            err = (created.stderr or created.stdout or "provider create failed").strip()
            raise RuntimeError(err[:300])
    else:
        update = _run(
            [openshell, "provider", "update", prov, "--credential", "RUN_TOKEN"],
            timeout=20,
            env=env,
        )
        if update.returncode != 0:
            _run([openshell, "provider", "delete", prov], timeout=20)
            created = _run(
                [
                    openshell,
                    "provider",
                    "create",
                    "--name",
                    prov,
                    "--type",
                    PROVIDER_TYPE,
                    "--credential",
                    "RUN_TOKEN",
                ],
                timeout=20,
                env=env,
            )
            if created.returncode != 0:
                err = (created.stderr or created.stdout or "provider create failed").strip()
                raise RuntimeError(err[:300])
    # Update used to return before attach. Egress then left
    # openshell:resolve:env:RUN_TOKEN unresolved and the agent turn died.
    legacy = f"{sandbox}-run"
    if legacy != prov:
        _run([openshell, "sandbox", "provider", "detach", sandbox, legacy], timeout=20)
    attached = _run(
        [openshell, "sandbox", "provider", "attach", sandbox, prov],
        timeout=20,
        env=env,
    )
    if attached.returncode != 0:
        err = (attached.stderr or attached.stdout or "provider attach failed").strip()
        raise RuntimeError(err[:300])
    _allow_tools(sandbox)
    _project_run_token_placeholder(sandbox)


def destroy_sandbox(name: str) -> None:
    if is_protected(name):
        raise RuntimeError("refusing to destroy gold or unknown sandbox")
    with _lock(name):
        _destroy_unlocked(name)


def normalize_history(history: object) -> list[dict[str, str]]:
    """Keep role and content only. Extra keys, including an evidence blob, are dropped."""
    if not isinstance(history, list):
        return []
    turns: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        content = str(item.get("content") or "").strip()[:2000]
        if not content:
            continue
        turns.append({"role": role, "content": content})
    return turns[-8:]


def earlier_block(history: object) -> str:
    turns = normalize_history(history)
    if not turns:
        return ""
    lines = ["Earlier in this chat:"]
    for turn in turns:
        speaker = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {turn['content']}")
    return "\n".join(lines) + "\n\n"


_TOOL_MENTIONS = ("labs", "meds", "conditions", "encounters", "allergies", "diet", "notes", "imaging")
_TOOL_MENTION = re.compile(
    r"(?<![A-Za-z0-9_])/(" + "|".join(_TOOL_MENTIONS) + r")\b",
    re.I,
)


def mentioned_tools(question: str) -> list[str]:
    found: list[str] = []
    for match in _TOOL_MENTION.finditer(question or ""):
        token = match.group(1).lower()
        if token not in found:
            found.append(token)
    return found


def turn_prompt(question: str, patient_key: str | None, history: object = None) -> str:
    """Ask the model which chart lookups this question needs. The host does not choose them."""
    key = patient_key or ""
    key_line = f"Patient key: {patient_key}\n" if patient_key else ""
    pointed = mentioned_tools(question)
    pointed_line = (
        f"The clinician pointed at these lookups: {', '.join(pointed)}. "
        "Still run any other lookup the question needs.\n"
        if pointed
        else ""
    )
    return (
        "You are the Patient360 clinical assistant. "
        "You decide which chart lookups this question needs, then run only those. "
        "Execute this script, not tool_search or invented tool ids.\n"
        f"python3 {SKILL_SCRIPT} notes "
        f'\'{{"patient_key":"{key}","question":"QUESTION"}}\'\n'
        f"python3 {SKILL_SCRIPT} query "
        f'\'{{"patient_key":"{key}","dataset":"DATASET"}}\'\n'
        f"python3 {SKILL_SCRIPT} imaging "
        f'\'{{"patient_key":"{key}"}}\'\n'
        f"python3 {SKILL_SCRIPT} query "
        '\'{"dataset":"DATASET","aggregate":{"group_by":["code"],"measure":"count"}}\'\n'
        "DATASET is one of labs, meds, conditions, encounters, allergies, diet. "
        "Optional query filters are since, until, code, category, and active_only. "
        "Use notes for narrative, summaries, and documents. "
        "Use query for measurements, medications, conditions, visits, allergies, or diet. "
        "Use imaging for studies, reports, and allowed_classes. Do not request pixels or media. "
        "If the user asks which overlays or VISTA classes are possible, call imaging without "
        "classes, then answer in your own words from allowed_classes. Do not recite a fixed "
        "template. Only add classes and study_id when they ask to segment a named organ. "
        "Use the aggregate form for a suppressed count. Omit patient_key. "
        "group_by is a column such as code, category, sex, or birth_year. "
        "A count is not one patient's chart. A 404 means this role cannot count. "
        "Run more than one lookup when the question needs more than one. "
        "The script already sends Authorization: Bearer openshell:resolve:env:RUN_TOKEN. "
        "Cite cite_ids from the tool results you chose. "
        "If a cite_id contains the patient key, cite note_<the rest> with hyphens changed to underscores. "
        "If a tool returns HTTP 200 with rows, notes, or reports, summarize those facts. "
        "Say you have no authorized evidence only when every lookup you needed returns nothing or 404. "
        "Do not invent values or names. Do not mention tokens, sandboxes, or policies.\n\n"
        f"{key_line}"
        f"{earlier_block(history)}"
        f"{pointed_line}"
        f"Question: {question}"
    )


def _usable_answer(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return False
    if low.startswith("llm request failed") or "/approve" == low:
        return False
    if "couldn't generate a response" in low:
        return False
    return True


def _exec_tool(sandbox: str, kind: str, payload: dict) -> dict | None:
    for attempt in range(3):
        proc = _run(
            [
                _which("nemoclaw"),
                sandbox,
                "exec",
                "--no-tty",
                "--",
                "python3",
                SKILL_SCRIPT,
                kind,
                json.dumps(payload),
            ],
            timeout=45,
        )
        raw = (proc.stdout or "").strip()
        start = raw.find("{")
        if start < 0:
            return None
        try:
            body = json.loads(raw[start:])
        except json.JSONDecodeError:
            return None
        if not isinstance(body, dict):
            return None
        # Provider attachment/refresh returns before its egress credentials propagate.
        if body.get("error") == "credential_injection_failed" and attempt < 2:
            sleep(2)
            continue
        if proc.returncode != 0 or "error" in body or "issue" in body:
            return None
        return body
    return None


def _agent(sandbox: str, message: str, *, session_id: str | None = None) -> str:
    session = session_id or agent_session_id(sandbox)
    proc = _run(
        [
            _which("nemoclaw"),
            sandbox,
            "agent",
            "-m",
            message,
            "--agent",
            AGENT,
            "--session-id",
            session,
            "--json",
        ],
        timeout=TIMEOUT,
    )
    raw = (proc.stdout or "").strip()
    try:
        text = _agent_text(json.loads(raw)) if raw.startswith("{") else raw
    except json.JSONDecodeError:
        text = raw
    text = text.strip()
    if proc.returncode != 0:
        err = " ".join((proc.stderr or "").split())
        # OpenClaw marks a finished tool turn replayInvalid and exits 1
        # even when payloads already hold the assistant answer.
        if "replayInvalid=true" in err and _usable_answer(text):
            print(
                f"nemoclaw-turn: kept answer after replayInvalid sandbox={sandbox} chars={len(text)}",
                flush=True,
            )
            return text
        raise RuntimeError(
            f"NemoClaw agent command exited with code {proc.returncode}: {err[:220]}"
        )
    return text


def run_turn(sandbox: str, question: str, patient_key: str | None, history: object = None) -> str:
    if is_protected(sandbox):
        raise RuntimeError("refusing turn on gold or unknown sandbox")
    _project_run_token_placeholder(sandbox)
    prompt = turn_prompt(question, patient_key, history)
    # A failed Ask turn marks the OpenClaw session abandoned/replayInvalid.
    # History is already folded into the prompt, so each attempt gets a new session.
    last_error: Exception | None = None
    for attempt in range(2):
        sid = f"{agent_session_id(sandbox)}-{attempt}-{int(perf_counter() * 1000) % 1_000_000}"
        try:
            text = _agent(sandbox, prompt, session_id=sid)
        except RuntimeError as exc:
            last_error = exc
            continue
        if _usable_answer(text):
            return text
        print(f"nemoclaw-turn: unusable answer sandbox={sandbox} session={sid} chars={len(text)} head={text[:180]!r}", flush=True)
        last_error = RuntimeError("empty or unusable nemoclaw turn")
    raise last_error or RuntimeError("empty or unusable nemoclaw turn")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"nemoclaw-turn: {fmt % args}", flush=True)

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        prefix = "/v1/sandboxes/"
        if path.startswith(prefix):
            name = unquote(path[len(prefix) :]).strip()
            if not name or "/" in name:
                self._json(404, {"ready": False})
                return
            self._json(200, sandbox_liveness(name))
            return
        if path in {"", "/healthz", "/v1/health"}:
            self._json(
                200,
                {
                    "ok": True,
                    "gold": GOLD,
                    "agent": AGENT,
                    "tools_url": TOOLS_URL,
                    "nemoclaw": _which("nemoclaw"),
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        prefix = "/v1/sandboxes/"
        if not path.startswith(prefix):
            self._json(404, {"error": "not_found"})
            return
        name = unquote(path[len(prefix) :]).strip()
        if not name or is_protected(name):
            self._json(403, {"error": "protected_sandbox"})
            return
        threading.Thread(target=destroy_sandbox, args=(name,), daemon=True).start()
        self._json(202, {"ok": True, "sandbox": name})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        path = self.path.rstrip("/")
        if path == "/v1/sandboxes":
            sid = str(payload.get("sid") or "").strip()
            name = str(payload.get("sandbox") or "").strip()
            started = perf_counter()
            try:
                name = name or session_sandbox_name(sid)
                sandbox = provision(name)
            except Exception as exc:
                self._json(503, {"error": exc.__class__.__name__, "detail": str(exc)[:300]})
                return
            print(
                f"nemoclaw-turn: sandbox_ensure sandbox={sandbox} elapsed={perf_counter() - started:.2f}s",
                flush=True,
            )
            self._json(200, {"ok": True, "sandbox_id": sandbox})
            return
        if path == "/v1/credentials":
            sandbox = str(payload.get("sandbox") or "").strip()
            token = str(payload.get("value") or "").strip()
            if not sandbox or not token:
                self._json(400, {"error": "sandbox_and_value_required"})
                return
            if is_protected(sandbox):
                self._json(403, {"error": "protected_sandbox"})
                return
            try:
                upsert_run_token(sandbox, token)
            except Exception as exc:
                self._json(502, {"error": exc.__class__.__name__, "detail": str(exc)[:300]})
                return
            self._json(200, {"ok": True, "sandbox": sandbox})
            return
        if path == "/v1/turns":
            question = str(payload.get("input") or payload.get("question") or "").strip()
            sandbox = str(payload.get("sandbox") or "").strip()
            patient_key = str(payload.get("patient_key") or "").strip() or None
            if payload.get("context") or payload.get("evidence"):
                self._json(400, {"error": "evidence_not_allowed"})
                return
            history = payload.get("history")
            if history is not None and not isinstance(history, list):
                self._json(400, {"error": "history_invalid"})
                return
            if not question or not sandbox:
                self._json(400, {"error": "sandbox_and_question_required"})
                return
            if is_protected(sandbox):
                self._json(403, {"error": "protected_sandbox"})
                return
            _turn_stages.items = []
            started = perf_counter()
            try:
                answer = run_turn(sandbox, question, patient_key, normalize_history(history))
            except Exception as exc:
                print(
                    f"nemoclaw-turn: turn sandbox={sandbox} {_format_stages(getattr(_turn_stages, 'items', None))} "
                    f"total={perf_counter() - started:.2f}s error={exc.__class__.__name__}: {str(exc)[:200]}",
                    flush=True,
                )
                self._json(502, {"error": exc.__class__.__name__, "detail": str(exc)[:300]})
                return
            print(
                f"nemoclaw-turn: turn sandbox={sandbox} session={agent_session_id(sandbox)} "
                f"{_format_stages(getattr(_turn_stages, 'items', None))} total={perf_counter() - started:.2f}s",
                flush=True,
            )
            self._json(200, {"answer": answer})
            return
        self._json(404, {"error": "not_found"})


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"nemoclaw-turn listening on {HOST}:{PORT} gold={GOLD} tools={TOOLS_URL}", flush=True)
    server.serve_forever()
