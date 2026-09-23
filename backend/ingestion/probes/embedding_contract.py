#!/usr/bin/env python3
"""Probe the live text embedding contract with harmless generated inputs only.

Requires tokenizers==0.22.2 and the downloaded model tokenizer.json.
Does not read notes, write stores, or change the serving configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import tokenizers


MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
SAMPLES = [
    "The library opens at nine in the morning.",
    "word",
    "word ",
    "## Plan\n\nContinue the exercise programme.",
    "[PERSON] reports no pain.",
    "Café — temperature 37.2 °C.",
    "  repeated\tspaces\n\nremain.",
    "<|begin_of_text|>literal token marker",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tokenizer = tokenizers.Tokenizer.from_file(str(args.tokenizer))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    base = args.url.rstrip("/")

    def get(path: str) -> dict:
        with urlopen(base + path, timeout=10) as response:
            return json.load(response)

    def count(text: str, mode: str) -> int:
        # Count locally; do NOT prepend this prefix to the HTTP input.
        return len(tokenizer.encode(f"{mode}: {text}", add_special_tokens=True).ids)

    def probe(texts: list[str], mode: str, expected_status: int = 200) -> dict:
        request = Request(
            base + "/v1/embeddings",
            data=json.dumps({
                "model": MODEL, "input": texts, "input_type": mode,
                "encoding_format": "float", "truncate": "NONE",
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=60) as response:
                status, result = response.status, json.load(response)
        except HTTPError as error:
            status, result = error.code, json.loads(error.read())
        assert status == expected_status, (mode, status, expected_status)
        record = {
            "mode": mode, "inputs": len(texts), "status": status,
            "formatted_tokens": [count(text, mode) for text in texts],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }
        if status != 200:
            assert "data" not in result, "Rejected request returned partial vectors"
            assert "4097 exceeds model maximum 4096" in result.get("message", "")
            record["error"] = result
            return record
        assert result["model"] == MODEL
        rows = result["data"]
        assert len(rows) == len(texts)
        assert sorted(row["index"] for row in rows) == list(range(len(texts)))
        norms = []
        for row in rows:
            vector = row["embedding"]
            assert len(vector) == 2048
            assert all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
            norm = math.sqrt(sum(value * value for value in vector))
            assert norm > 0
            norms.append(norm)
        assert result["usage"]["prompt_tokens"] == sum(record["formatted_tokens"])
        record.update({
            "dimensions": 2048, "indices": [row["index"] for row in rows],
            "norm_range": [min(norms), max(norms)], "usage": result["usage"],
        })
        return record

    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "url": base, "model": MODEL, "tokenizers_version": tokenizers.__version__,
        "tokenizer_sha256": hashlib.sha256(args.tokenizer.read_bytes()).hexdigest(),
        "ready": get("/v1/health/ready"), "runtime": get("/v1/version"),
        "samples": [], "boundaries": [], "batches": [],
    }
    assert report["ready"].get("ready") is True
    for mode in ("passage", "query"):
        for text in SAMPLES:
            record = probe([text], mode)
            record.update({
                "text": text,
                "content_tokens": len(tokenizer.encode(text, add_special_tokens=False).ids),
            })
            report["samples"].append(record)
        for target in (512, 513, 4095, 4096, 4097):
            # This fixture has a predictable count; the assertion checks it.
            text = "word " * (target - (5 if mode == "passage" else 4))
            assert count(text, mode) == target
            report["boundaries"].append(probe([text], mode, 422 if target == 4097 else 200))
    for size in (1, 8, 16, 32):
        report["batches"].append(probe(["word " * 507] * size, "passage"))
    report["mixed_oversize_batch"] = probe(["hello", "word " * 4092], "passage", 422)
    report["result"] = "passed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"PASS: tokenizer counts, input boundaries, vectors and bounded batches; report: {args.output}")


if __name__ == "__main__":
    main()
