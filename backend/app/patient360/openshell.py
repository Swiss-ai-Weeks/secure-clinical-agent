"""OpenShell runtime: per-session sandbox, run-token register, one turn.

The live gateway is mTLS gRPC, not a public REST API. The backend container
cannot run `nemoclaw`. HTTP calls go to the host adapter at
PATIENT360_OPENSHELL_URL (/v1/sandboxes, /v1/credentials, /v1/turns).
Failures return None so /chat can refuse instead of substituting a local answer.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings

log = logging.getLogger(__name__)

GOLD_SANDBOX = "patient360"
SESSION_SANDBOX_PREFIX = "p360-s-"
_DESTROY_PREFIXES = (SESSION_SANDBOX_PREFIX, "p360-pool-", "p360-probe-")


def session_sandbox_name(sid: str) -> str:
    token = "".join(ch for ch in sid.lower() if ch.isalnum())[:12]
    if len(token) < 8:
        raise ValueError("sid too short for sandbox name")
    return f"{SESSION_SANDBOX_PREFIX}{token}"


def is_protected_sandbox(name: str) -> bool:
    """True for the gold box or any name we did not provision."""
    return name == GOLD_SANDBOX or not name.startswith(_DESTROY_PREFIXES)


async def ensure_sandbox(
    url: str, sid: str, *, sandbox: str | None = None, timeout: float = 600.0
) -> str:
    """Create or reuse the session sandbox. Returns the sandbox name."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{url.rstrip('/')}/v1/sandboxes",
            json={"sid": sid, "sandbox": sandbox or session_sandbox_name(sid)},
        )
        response.raise_for_status()
        body = response.json()
    name = str(body.get("sandbox_id") or body.get("sandbox") or "").strip()
    if not name or is_protected_sandbox(name):
        raise RuntimeError("adapter did not provision a session sandbox")
    return name


async def register_run_token(
    url: str, token: str, *, sandbox: str, timeout: float = 15.0
) -> bool:
    """Register this turn's JWT on the sandbox's generic OpenShell provider."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{url.rstrip('/')}/v1/credentials",
            json={"name": "RUN_TOKEN", "value": token, "sandbox": sandbox},
        )
    return response.status_code < 300


async def sandbox_turn(
    url: str,
    question: str,
    *,
    sandbox: str,
    patient_key: str | None = None,
    history: list[dict[str, str]] | None = None,
    timeout: float = 180.0,
) -> str:
    payload: dict[str, Any] = {"input": question, "sandbox": sandbox, "patient_key": patient_key}
    if history:
        payload["history"] = history
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{url.rstrip('/')}/v1/turns",
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    text = str(body.get("answer") or body.get("output") or body.get("text") or "").strip()
    if not text or text.lower().startswith("llm request failed"):
        raise RuntimeError("empty sandbox turn")
    return text


def sandbox_stamp(sandbox_id: str, generation: str) -> str:
    """Opaque id for one live sandbox. The name and generation stay on the server."""
    return hashlib.sha256(f"{sandbox_id}\n{generation}".encode()).hexdigest()[:32]


async def read_sandbox_generation(url: str, sandbox: str) -> str | None:
    """Generation of a ready session sandbox. Missing or not ready returns None. Does not create one."""
    if not url or is_protected_sandbox(sandbox):
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{url.rstrip('/')}/v1/sandboxes/{quote(sandbox)}")
        if response.status_code >= 300:
            return None
        body = response.json()
    except Exception as exc:
        log.warning("sandbox status failed: %s", exc.__class__.__name__)
        return None
    if not body.get("ready"):
        return None
    generation = str(body.get("generation") or "").strip()
    return generation or None


async def session_sandbox_status(settings: Settings, sandbox_id: str | None) -> dict[str, Any]:
    """Whether this session's sandbox is still the one a chat can return to."""
    if not sandbox_id or not settings.openshell_url:
        return {"active": False}
    generation = await read_sandbox_generation(settings.openshell_url, sandbox_id)
    if not generation:
        return {"active": False}
    return {"active": True, "stamp": sandbox_stamp(sandbox_id, generation)}


async def destroy_session_sandbox(settings: Settings, sandbox_id: str | None) -> bool:
    """Ask the host adapter to destroy a session sandbox. Never the gold box."""
    if not sandbox_id or is_protected_sandbox(sandbox_id):
        return False
    if not settings.openshell_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{settings.openshell_url.rstrip('/')}/v1/sandboxes/{sandbox_id}"
            )
        return response.status_code < 300
    except Exception as exc:
        log.warning("sandbox destroy failed: %s", exc.__class__.__name__)
        return False


def _agent_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        for item in payload:
            nested = _agent_text(item)
            if nested:
                return nested
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
        if key not in payload:
            continue
        nested = _agent_text(payload[key])
        if nested:
            return nested
    return ""


async def try_openshell_turn(
    settings: Settings,
    token: str,
    question: str,
    *,
    sandbox: str,
    patient_key: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    """One NemoClaw turn via the host adapter. No evidence dump, no gold box."""
    if not settings.openshell_url:
        log.warning("PATIENT360_OPENSHELL_URL is empty")
        return None
    if not sandbox or is_protected_sandbox(sandbox):
        log.warning("openshell turn refused: missing or protected sandbox")
        return None
    try:
        if not await register_run_token(settings.openshell_url, token, sandbox=sandbox):
            log.warning("openshell run token register rejected")
            return None
        return await sandbox_turn(
            settings.openshell_url,
            question,
            sandbox=sandbox,
            patient_key=patient_key,
            history=history,
        )
    except Exception as exc:
        log.warning("openshell HTTP turn failed: %s: %s", exc.__class__.__name__, exc)
        return None
