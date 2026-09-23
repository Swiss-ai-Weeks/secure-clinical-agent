#!/usr/bin/env python3
"""Call Patient360 /tools/* with the OpenShell RUN_TOKEN placeholder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = "http://host.openshell.internal:8088"
PLACEHOLDER_FILE = "/sandbox/.openclaw/workspace/skills/patient360-tools/.run_token_ref"
# Fresh OpenShell exec sees the live revision. The agent process does not, so it reads the file.
P360_PLACEHOLDER_SOURCE = "file"
CURL = "/usr/bin/curl"


def _scoped_placeholder(raw: str) -> str | None:
    text = raw.strip()
    if not text.startswith("openshell:resolve:env:"):
        return None
    name = text.rsplit(":", 1)[-1]
    if name == "RUN_TOKEN":
        return None
    if name.endswith("_RUN_TOKEN") and (
        name.startswith("v") or name.startswith("s")
    ):
        return text
    return None


def authorization() -> str:
    """Prefer the file written from a fresh exec. The agent env is stale or empty."""
    candidates: list[str] = []
    if Path(PLACEHOLDER_FILE).is_file():
        candidates.append(Path(PLACEHOLDER_FILE).read_text())
    candidates.append(os.environ.get("RUN_TOKEN") or "")
    for raw in candidates:
        scoped = _scoped_placeholder(raw)
        if scoped:
            return f"Bearer {scoped}"
    return "Bearer openshell:resolve:env:RUN_TOKEN"


PATHS = {
    "query": "/tools/query",
    "notes": "/tools/notes",
    "imaging": "/tools/imaging",
}


def post_tool(url: str, body: dict, timeout: int) -> tuple[int, str]:
    """POST via curl so OpenShell attributes rewrite to an allow-listed binary."""
    auth = authorization()
    scoped = auth.removeprefix("Bearer ").strip()
    payload = dict(body)
    # request_body_credential_rewrite only rewrites the body; keep the header too.
    if scoped.startswith("openshell:resolve:env:"):
        payload["openshell_resolve"] = scoped
    proc = subprocess.run(
        [
            CURL,
            "-sS",
            "--http1.1",
            "-m",
            str(timeout),
            "-H",
            f"Authorization: {auth}",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload),
            "-w",
            "\nHTTP_STATUS:%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = proc.stdout or ""
    status = 0
    if "HTTP_STATUS:" in raw:
        raw, _, tail = raw.rpartition("HTTP_STATUS:")
        try:
            status = int(tail.strip().split()[0])
        except ValueError:
            status = 502
    elif proc.returncode:
        err = (proc.stderr or proc.stdout or "curl failed").strip()
        return 502, err
    if status == 0:
        status = 200
    return status, raw


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in PATHS:
        print("usage: p360_tools.py query|notes|imaging '<json>'", file=sys.stderr)
        return 2
    kind = sys.argv[1]
    try:
        body = json.loads(sys.argv[2])
    except json.JSONDecodeError as exc:
        print(f"invalid json: {exc}", file=sys.stderr)
        return 2
    path = PATHS[kind]
    timeout = 300 if kind == "imaging" and body.get("classes") is not None else 30
    url = f"{BASE}{path}"
    raw = ""
    code = 0
    for attempt in range(3):
        try:
            code, raw = post_tool(url, body, timeout)
        except OSError as exc:
            print(f"tools unreachable: {exc.__class__.__name__}", file=sys.stderr)
            return 1
        if "credential_injection_failed" in raw and attempt < 2:
            time.sleep(2)
            continue
        sys.stdout.write(raw)
        return 1 if code >= 500 else 0
    sys.stdout.write(raw)
    return 1 if code >= 500 else 0


if __name__ == "__main__":
    raise SystemExit(main())
