#!/usr/bin/env python3
"""Run YAML cases against a live Patient360 backend. Offline tests use the ASGI harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CASES = Path(__file__).with_name("cases.yaml")


def load_cases() -> list[dict]:
    text = CASES.read_text(encoding="utf-8")
    cases: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("- id:"):
            if current:
                cases.append(current)
            current = {"id": line.split(":", 1)[1].strip()}
        elif current and line.startswith("  ") and ":" in line:
            key, _, value = line.strip().partition(":")
            current[key.strip()] = value.strip().strip('"')
    if current:
        cases.append(current)
    return cases


def summarize(results: list[dict]) -> dict:
    total = len(results)
    failed = sum(1 for r in results if r.get("result") == "fail")
    return {
        "count": total,
        "pass": sum(1 for r in results if r.get("result") == "pass"),
        "fail": failed,
        "partial": sum(1 for r in results if r.get("result") == "partial"),
        "asr": (failed / total) if total else 0.0,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--base-url", default="", help="If empty, print the catalog. Live run needs a session.")
    args = parser.parse_args()
    cases = load_cases()
    if args.list or not args.base_url:
        print(json.dumps({"count": len(cases), "ids": [c["id"] for c in cases]}, indent=2))
        return 0
    print(
        json.dumps(
            {
                "ok": False,
                "note": "Use GET /redteam on the backend (in-process suite) or pytest tests/test_redteam.py",
                "count": len(cases),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
