#!/usr/bin/env python3
"""Seed OpenFGA tuples and consent_granted rows. No bulk grants on the leftover Synthea 97.

Hackathon showcase (the three approved clinical examples only):
  Chen attending          all three
  Rivera care_team        all three
  Okafor consultant       hypertension + pneumonia
  Ward w_3b admission     diabetes (kitchen) plus demo p_101
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def demo_relative_windows(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    return [
        {
            "user": "user:u_okafor",
            "relation": "consultant",
            "object": "patient:p_101",
            "start": (now - timedelta(hours=1)).isoformat(),
            "expiry": (now + timedelta(hours=2)).isoformat(),
            "kind": "demo_window",
        },
        {
            "user": "user:u_lindqvist",
            "relation": "staff",
            "object": "ward:w_3b",
            "start": now.replace(hour=6, minute=0, second=0, microsecond=0).isoformat(),
            "expiry": now.replace(hour=18, minute=0, second=0, microsecond=0).isoformat(),
            "kind": "shift",
        },
    ]


SHOWCASE_WINDOW = ("2026-09-01T00:00:00+00:00", "2027-09-01T00:00:00+00:00")
SHOWCASE_SYNTHEA_KEYS = (
    "p_56fc60ea6ccd458496bba589b932e26d",  # diabetes
    "p_b1ef4e59dd984d828f102e37a3a5cd77",  # hypertension
    "p_485ba8c8597d4c5cb0fbda55317119a3",  # pneumonia
)


def _windowed(
    user: str, relation: str, patient_key: str, *, kind: str
) -> dict[str, Any]:
    start, expiry = SHOWCASE_WINDOW
    return {
        "user": user,
        "relation": relation,
        "object": f"patient:{patient_key}",
        "start": start,
        "expiry": expiry,
        "kind": kind,
        "seeded": True,
    }


def synthea_demo_attending(patient_keys: list[str]) -> list[dict[str, Any]]:
    """u_chen attending on the three approved Synthea demonstration keys only."""
    return [_windowed("user:u_chen", "attending", key, kind="synthea_demo") for key in patient_keys]


def showcase_care_team(patient_keys: list[str]) -> list[dict[str, Any]]:
    """Nurse Rivera covers the live Synthea charts for the care-team persona."""
    return [_windowed("user:u_rivera", "care_team", key, kind="synthea_care_team") for key in patient_keys]


def showcase_consultant(patient_keys: list[str]) -> list[dict[str, Any]]:
    """Cardiology consult on hypertension and pneumonia (not the diabetes index)."""
    consult = [key for key in patient_keys if key in SHOWCASE_SYNTHEA_KEYS[1:]]
    if not consult and len(patient_keys) > 1:
        consult = patient_keys[1:]
    return [_windowed("user:u_okafor", "consultant", key, kind="synthea_consultant") for key in consult]


def worker_placements(
    admitted_keys: list[str] | None = None,
    *,
    ward: str = "w_3b",
    staff_user: str = "u_lindqvist",
) -> list[dict[str, Any]]:
    """Worker-owned ward placements. Not consents; audit detail.kind = admission/roster."""
    now = datetime.now(UTC)
    start = now.isoformat()
    expiry = (now + timedelta(days=14)).isoformat()
    writes = [
        {
            "user": f"ward:{ward}",
            "relation": "admitted_to",
            "object": f"patient:{key}",
            "start": start,
            "expiry": expiry,
            "kind": "admission",
        }
        for key in (admitted_keys or ["p_101"])
    ]
    writes.append(
        {
            "user": f"user:{staff_user}",
            "relation": "staff",
            "object": f"ward:{ward}",
            "start": start,
            "expiry": expiry,
            "kind": "roster",
        }
    )
    return writes


def consent_rows(writes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """consent_granted projections for demo/synthea care tuples (not ward placements)."""
    skip = {"admission", "roster", "shift"}
    return [
        {
            "event_type": "consent_granted",
            "agent_user": "system:seed_grants",
            "entity_patient": w["object"].split(":", 1)[1],
            "detail": {
                "seeded": True,
                "kind": w.get("kind"),
                "user": w["user"],
                "relation": w["relation"],
                "start": w.get("start"),
                "expiry": w.get("expiry"),
            },
        }
        for w in writes
        if w.get("kind") not in skip
    ]


def plan(
    synthea_demo_keys: list[str] | None = None,
    *,
    admitted_keys: list[str] | None = None,
) -> dict[str, Any]:
    keys = list(synthea_demo_keys) if synthea_demo_keys is not None else list(SHOWCASE_SYNTHEA_KEYS)
    if admitted_keys is None:
        admitted_keys = ["p_101", *([keys[0]] if keys else [])]
    writes = (
        demo_relative_windows()
        + synthea_demo_attending(keys)
        + showcase_care_team(keys)
        + showcase_consultant(keys)
        + worker_placements(admitted_keys)
    )
    return {
        "writes": writes,
        "consents": consent_rows(writes),
        "bulk_remaining": 0,
        "note": "Do not grant care relations on the leftover Synthea patients.",
    }


def rfc3339(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = value.strip()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    if text.endswith("Z") and "." in text:
        return text.split(".", 1)[0] + "Z"
    return text


def discover_store(url: str, token: str, name: str) -> str:
    req = Request(f"{url.rstrip('/')}/stores")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    for store in body.get("stores") or []:
        if store.get("name") == name:
            return store["id"]
    raise RuntimeError(f"openfga store {name} not found")


def write_openfga(url: str, token: str, store_id: str, writes: list[dict[str, Any]]) -> int:
    """Write tuples one by one so an existing demo window does not abort the Synthea grants."""
    written = 0
    for w in writes:
        item: dict[str, Any] = {"user": w["user"], "relation": w["relation"], "object": w["object"]}
        if w.get("start") and w.get("expiry"):
            item["condition"] = {
                "name": "active_window",
                "context": {"start": rfc3339(w["start"]), "expiry": rfc3339(w["expiry"])},
            }
        req = Request(
            f"{url.rstrip('/')}/stores/{quote(store_id)}/write",
            data=json.dumps({"writes": {"tuple_keys": [item]}}).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urlopen(req, timeout=30) as resp:
                resp.read()
            written += 1
        except HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            if "already exists" in text or "write_failed_due_to_invalid_input" in text:
                continue
            print(
                json.dumps(
                    {
                        "write_error": exc.code,
                        "user": w["user"],
                        "relation": w["relation"],
                        "object": w["object"],
                        "detail": text[:400],
                    }
                ),
                file=sys.stderr,
            )
            raise
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthea-demo-key", action="append", default=None)
    parser.add_argument("--admitted-key", action="append", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--openfga-url", default=os.environ.get("PATIENT360_OPENFGA_URL", ""))
    parser.add_argument("--openfga-key", default=os.environ.get("PATIENT360_OPENFGA_KEY", ""))
    parser.add_argument("--store-name", default="patient360-grants")
    args = parser.parse_args(argv)
    body = plan(args.synthea_demo_key, admitted_keys=args.admitted_key)
    if args.dry_run or not args.openfga_url:
        print(json.dumps(body, indent=2))
        return 0
    store_id = discover_store(args.openfga_url, args.openfga_key, args.store_name)
    written = write_openfga(args.openfga_url, args.openfga_key, store_id, body["writes"])
    print(json.dumps({"ok": True, "store_id": store_id, "written": written, "bulk_remaining": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
