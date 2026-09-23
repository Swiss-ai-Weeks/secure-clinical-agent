"""Tokenizer-aware, unpublished note preparation and embedding admission.

This module produces preparation artifacts, not Qdrant publication identities.
It never loads remote tokenizer code or falls back to word counts.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
TOKENIZER_VERSION = "0.22.2"
TOKENIZER_SHA256 = "0fb8bdddbd4c4ffa55e51d5b0393611e3df49dd86a31189ef5dcb750cf3da399"
CONTENT_LIMIT = 512
OVERLAP_LIMIT = 64
INPUT_LIMIT = 4096
DIMENSIONS = 2048
HEADING = re.compile(r"(?m)^(?P<heading> {0,3}#{1,6}[ \t]+[^\r\n]+)(?:\r?\n|$)")
BOUNDARY = re.compile(r"\n[ \t\r]*\n|[.!?](?:[ \t]+|\r?\n|$)")


class VectorPreparationError(ValueError):
    """A safe reason code; never include source text or response bodies."""


def digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def input_text(chunk: dict[str, Any]) -> str:
    heading = chunk["heading_context"]
    return f"{heading}\n\n{chunk['text']}" if heading else chunk["text"]


class ModelTokenizer:
    def __init__(self, path: str | Path, *, expected_sha256: str = TOKENIZER_SHA256):
        if not path:
            raise VectorPreparationError("tokenizer_required")
        try:
            data = Path(path).read_bytes()
        except OSError:
            raise VectorPreparationError("tokenizer_unavailable") from None
        self.sha256 = hashlib.sha256(data).hexdigest()
        if self.sha256 != expected_sha256:
            raise VectorPreparationError("tokenizer_hash_mismatch")
        try:
            import tokenizers
        except ImportError:
            raise VectorPreparationError("tokenizer_dependency_missing") from None
        if tokenizers.__version__ != TOKENIZER_VERSION:
            raise VectorPreparationError("tokenizer_library_mismatch")
        try:
            self._tokenizer = tokenizers.Tokenizer.from_str(data.decode())
        except Exception:
            raise VectorPreparationError("tokenizer_invalid") from None
        self._tokenizer.no_padding()
        self._tokenizer.no_truncation()
        self.policy_id = digest(
            {
                "version": "section-chunks-1",
                "tokenizer_sha256": self.sha256,
                "tokenizers": TOKENIZER_VERSION,
                "content_limit": CONTENT_LIMIT,
                "overlap_limit": OVERLAP_LIMIT,
                "offsets": "unicode-code-points-half-open",
                "heading": "nearest-atx-heading-exact-plus-two-newlines",
                "boundaries": "paragraph-or-sentence-then-token-offset",
            }
        )

    def encode(self, text: str):
        return self._tokenizer.encode(text, add_special_tokens=False)

    def content_count(self, text: str) -> int:
        return len(self.encode(text).ids)

    def input_count(self, text: str, mode: str = "passage") -> int:
        if mode not in ("passage", "query"):
            raise VectorPreparationError("invalid_input_type")
        return len(self._tokenizer.encode(f"{mode}: {text}", add_special_tokens=True).ids)

    def admit(self, text: str, mode: str = "passage") -> tuple[int, int]:
        if not isinstance(text, str) or not text.strip():
            raise VectorPreparationError("empty_embedding_input")
        content, total = self.content_count(text), self.input_count(text, mode)
        if mode == "passage" and content > CONTENT_LIMIT:
            raise VectorPreparationError("chunk_token_limit")
        # Conservative byte bound also satisfies the measured ASCII character bound.
        if total > INPUT_LIMIT or len(text.encode()) > 65536:
            raise VectorPreparationError("serving_input_limit")
        return content, total


@dataclass(frozen=True)
class PreparedChunk:
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int
    heading_context: str
    heading_start_offset: int | None
    heading_end_offset: int | None
    content_token_count: int
    input_token_count: int
    embedding_input_sha256: str
    preparation_chunk_id: str


def _sections(text: str):
    headings = list(HEADING.finditer(text))
    if not headings:
        yield 0, len(text), None
        return
    if headings[0].start():
        yield 0, headings[0].start(), None
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        if text[match.end() : end].strip():
            yield match.end(), end, match.span("heading")
        else:
            # A heading-only section is source content too; cite it as the body.
            yield match.start(), end, None


def chunk_note(text: str, tokenizer: ModelTokenizer, *, note_id: str, deid_version: str) -> list[dict]:
    if not text.strip():
        return []
    preparation_id = digest(
        {
            "note_id": note_id,
            "sanitized_text": text,
            "deid_version": deid_version,
            "chunk_policy_id": tokenizer.policy_id,
        }
    )
    chunks = []
    for section_start, section_end, heading_span in _sections(text):
        if not text[section_start:section_end].strip():
            continue
        heading = text[slice(*heading_span)] if heading_span else ""
        prefix = heading + "\n\n" if heading else ""
        start = section_start
        covered_until = start
        while start < section_end:
            remainder = text[start:section_end]
            encoded = tokenizer.encode(remainder)
            # Token offsets may repeat for Unicode bytes. Slice only at code points,
            # and always retokenize the complete heading+body before admitting it.
            candidates = sorted({end for _, end in encoded.offsets if end > 0} | {len(remainder)})
            initial = max(1, CONTENT_LIMIT - tokenizer.content_count(prefix))
            cut = encoded.offsets[min(initial, len(encoded.offsets)) - 1][1] if encoded.offsets else 0
            candidates = [end for end in candidates if end <= max(cut, 1)]
            fitting = next(
                (
                    end
                    for end in reversed(candidates)
                    if tokenizer.content_count(prefix + remainder[:end]) <= CONTENT_LIMIT
                ),
                None,
            )
            if fitting is None:
                raise VectorPreparationError("heading_or_body_exceeds_budget")
            end = start + fitting
            if end <= covered_until:
                start = covered_until
                continue
            if end < section_end:
                boundaries = [start + m.end() for m in BOUNDARY.finditer(text[start:end])]
                if boundaries:
                    preferred = boundaries[-1]
                    if (
                        preferred > covered_until
                        and tokenizer.content_count(prefix + text[start:preferred]) <= CONTENT_LIMIT
                    ):
                        end = preferred
            body = text[start:end]
            if not body.strip():
                # Keep whitespace with subsequent content; never emit empty vectors.
                # Excessive whitespace is a preparation failure, not silent trimming.
                raise VectorPreparationError("empty_chunk_body")
            content, total = tokenizer.admit(prefix + body)
            input_hash = hashlib.sha256((prefix + body).encode()).hexdigest()
            chunk_id = digest(
                {
                    "preparation_id": preparation_id,
                    "index": len(chunks),
                    "start": start,
                    "end": end,
                    "heading_span": heading_span,
                    "embedding_input_sha256": input_hash,
                }
            )
            chunks.append(
                asdict(
                    PreparedChunk(
                        len(chunks),
                        body,
                        start,
                        end,
                        heading,
                        heading_span[0] if heading_span else None,
                        heading_span[1] if heading_span else None,
                        content,
                        total,
                        input_hash,
                        chunk_id,
                    )
                )
            )
            covered_until = end
            if end == section_end:
                break
            offsets = tokenizer.encode(body).offsets
            overlap_start = end
            for relative in sorted({s for s, _ in offsets if 0 < s < len(body)}, reverse=True):
                if tokenizer.content_count(body[relative:]) > OVERLAP_LIMIT:
                    break
                overlap_start = start + relative
            # Each next window must extend the source coverage, even for tiny budgets.
            start = overlap_start if overlap_start > start else end
    return chunks


def validate_response(response: Any, model: str, count: int, expected_tokens: int) -> list[list[float]]:
    if not isinstance(response, dict) or response.get("model") != model:
        raise VectorPreparationError("embedding_model_mismatch")
    rows = response.get("data")
    if not isinstance(rows, list) or len(rows) != count:
        raise VectorPreparationError("embedding_count_mismatch")
    by_index = {}
    for row in rows:
        if not isinstance(row, dict):
            raise VectorPreparationError("embedding_row_invalid")
        index = row.get("index")
        if type(index) is not int or not 0 <= index < count or index in by_index:
            raise VectorPreparationError("embedding_index_invalid")
        vector = row.get("embedding")
        if not isinstance(vector, list) or len(vector) != DIMENSIONS:
            raise VectorPreparationError("embedding_dimension_mismatch")
        try:
            valid = all(type(x) in (int, float) and math.isfinite(x) for x in vector)
        except (OverflowError, TypeError):
            valid = False
        if not valid or not any(x != 0 for x in vector):
            raise VectorPreparationError("embedding_vector_invalid")
        by_index[index] = vector
    usage = response.get("usage")
    if not isinstance(usage, dict) or type(usage.get("prompt_tokens")) is not int:
        raise VectorPreparationError("embedding_usage_missing")
    if usage["prompt_tokens"] != expected_tokens:
        raise VectorPreparationError("embedding_token_count_mismatch")
    return [by_index[index] for index in range(count)]


def embed_inputs(
    texts: list[str],
    tokenizer: ModelTokenizer,
    request,
    *,
    model: str = MODEL,
    mode: str = "passage",
    batch_size: int = 8,
) -> list[list[float]]:
    if model != MODEL:
        raise VectorPreparationError("unsupported_embedding_model")
    if type(batch_size) is not int or not 1 <= batch_size <= 32:
        raise VectorPreparationError("invalid_embedding_batch_size")
    # Validate the entire set before the first outbound request.
    counts = [tokenizer.admit(text, mode)[1] for text in texts]
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        body = {
            "model": model,
            "input": batch,
            "input_type": mode,
            "encoding_format": "float",
            "truncate": "NONE",
        }
        try:
            response = request(body)
        except Exception:
            raise VectorPreparationError("embedding_service_unavailable") from None
        vectors.extend(
            validate_response(response, model, len(batch), sum(counts[start : start + batch_size]))
        )
    return vectors
