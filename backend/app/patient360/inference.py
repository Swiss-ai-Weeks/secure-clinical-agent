"""OpenAI-compatible chat completions client (Nemotron Nano)."""

from __future__ import annotations

from typing import Any

import httpx

def render_evidence(evidence: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in evidence:
        cite = item.get("cite") or item.get("id") or item.get("sourceId") or ""
        label = item.get("label") or ""
        text = item.get("text") or ""
        if not text:
            continue
        lines.append(f"[{cite}] {label}: {text}")
    return "\n".join(lines)


def chat_payload(model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Nemotron 3 Nano thinks by default; thinking can consume the whole token budget."""
    return {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 800,
        "chat_template_kwargs": {"enable_thinking": False},
    }


async def complete_chat(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    timeout: float = 90.0,
) -> str:
    """POST {url}/v1/chat/completions. Raises on transport or empty content."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{url.rstrip('/')}/v1/chat/completions",
            json=chat_payload(model, messages),
        )
        response.raise_for_status()
        body = response.json()
    choice = (body.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError(f"empty completion ({choice.get('finish_reason') or 'unknown'})")
    return content


async def resolve_model(url: str, configured: str, *, timeout: float = 10.0) -> str:
    if configured:
        return configured
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{url.rstrip('/')}/v1/models")
        response.raise_for_status()
        rows = response.json().get("data") or []
    if not rows:
        raise RuntimeError("no models")
    return str(rows[0].get("id") or "")
