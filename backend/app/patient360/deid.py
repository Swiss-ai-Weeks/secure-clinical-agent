"""Note de-identification (wayfinder 07). Presidio is optional; regex + hints always run.

Worker-only identity hints never enter embeddings, payloads, citations, or ordinary logs.
This is not a claim of complete anonymization.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID, uuid5

DEID_VERSION = "p360-deid-1.0"
NOTES_NAMESPACE = UUID("3c0a1f5e-8b2d-4e91-9c47-2a6f0d8e1b33")
CHUNK_TOKENS = 512
CHUNK_OVERLAP = 64
ATTACK_MARK = "[EVALUATION ATTACK PASSAGE]"

RACE_ETHNICITY = (
    "non-hispanic",
    "nonhispanic",
    "hispanic",
    "african american",
    "native american",
    "pacific islander",
    "white",
    "black",
    "asian",
    "latino",
    "latina",
    "latinx",
)

PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
MRN_RE = re.compile(r"\bMRN[- ]?[A-Z0-9]{4,}\b", re.I)
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LONG_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}\b",
    re.I,
)
AGE_RE = re.compile(r"\b(\d{2,3})\s*[- ]?year[- ]olds?\b", re.I)
OPENING_BORN_RE = re.compile(
    r"(Patient is a\s+\d+\s+year-old[^.]*?)(born\s+[^.]+)",
    re.I,
)


@dataclass(frozen=True)
class IdentityHints:
    names: tuple[str, ...] = ()
    dob_strings: tuple[str, ...] = ()
    mrns: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()


@dataclass
class Chunk:
    chunk_index: int
    text: str
    start: int
    end: int
    point_id: str


@dataclass
class SanitizeResult:
    text: str
    ok: bool
    canary_hits: list[str] = field(default_factory=list)
    deid_version: str = DEID_VERSION


def _replace_ci(text: str, needle: str, token: str) -> str:
    if not needle:
        return text
    return re.sub(re.escape(needle), token, text, flags=re.I)


def _optional_presidio(text: str) -> str:
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        from presidio_anonymizer.entities import OperatorConfig
    except ImportError:
        return text
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    results = analyzer.analyze(
        text=text,
        language="en",
        entities=["PERSON", "LOCATION", "PHONE_NUMBER", "EMAIL_ADDRESS"],
    )
    ops = {
        "PERSON": OperatorConfig("replace", {"new_value": "<PERSON>"}),
        "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE>"}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL>"}),
        "LOCATION": OperatorConfig("replace", {"new_value": "<LOCATION>"}),
    }
    return anonymizer.anonymize(text=text, analyzer_results=results, operators=ops).text


def sanitize(text: str, hints: IdentityHints | None = None) -> SanitizeResult:
    """De-identify a whole note. Clinical event dates that are not a known DOB stay."""
    hints = hints or IdentityHints()
    out = text
    for name in sorted(hints.names, key=len, reverse=True):
        out = _replace_ci(out, name, "<PERSON>")
    for dob in hints.dob_strings:
        out = _replace_ci(out, dob, "<DOB>")
    for mrn in hints.mrns:
        out = _replace_ci(out, mrn, "<ID>")
    for phone in hints.phones:
        out = _replace_ci(out, phone, "<PHONE>")
    out = OPENING_BORN_RE.sub(lambda m: f"{m.group(1)}born <DOB>", out)
    for phrase in sorted(RACE_ETHNICITY, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(phrase)}\b", "<ETH>", out, flags=re.I)

    def _age(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return "90+ year-old" if n >= 90 else m.group(0)

    out = AGE_RE.sub(_age, out)
    out = EMAIL_RE.sub("<EMAIL>", out)
    out = MRN_RE.sub("<ID>", out)
    out = PHONE_RE.sub("<PHONE>", out)
    # Exact ISO dates that match a known DOB only (hints already replaced). Leave others.
    out = _optional_presidio(out)

    hits = canary_hits(out, hints)
    return SanitizeResult(text=out, ok=not hits, canary_hits=hits)


def canary_hits(text: str, hints: IdentityHints) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for value in (*hints.names, *hints.dob_strings, *hints.mrns, *hints.phones, *hints.source_ids):
        if value and value.lower() in lowered:
            hits.append("identifier")
            break
    return hits


def _load_tokenizer(path: str | None):
    if not path:
        return None
    try:
        from tokenizers import Tokenizer
    except ImportError:
        return None
    from pathlib import Path

    if not Path(path).is_file():
        return None
    return Tokenizer.from_file(path)


def _token_spans(text: str, tokenizer) -> list[tuple[int, int]]:
    """Character spans for each content token. Offsets refer to exact `text`."""
    if tokenizer is not None:
        encoded = tokenizer.encode(text, add_special_tokens=False)
        spans = [(s, e) for s, e in encoded.offsets if e > s]
        if spans:
            return spans
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def chunk_text(
    text: str,
    note_id: str,
    *,
    deid_version: str = DEID_VERSION,
    heading: str = "",
    tokenizer_path: str | None = None,
) -> list[Chunk]:
    """512-token content windows with up to 64-token overlap. Heading is repeated per chunk."""
    if not text.strip():
        return []
    tokenizer = _load_tokenizer(tokenizer_path)
    heading_prefix = f"{heading.strip()}\n\n" if heading.strip() else ""
    heading_budget = len(_token_spans(heading_prefix, tokenizer)) if heading_prefix else 0
    body_budget = max(1, CHUNK_TOKENS - heading_budget)
    spans = _token_spans(text, tokenizer)
    if not spans:
        return []
    chunks: list[Chunk] = []
    start_i = 0
    index = 0
    while start_i < len(spans):
        end_i = min(len(spans), start_i + body_budget)
        start, end = spans[start_i][0], spans[end_i - 1][1]
        piece = heading_prefix + text[start:end]
        point_id = str(uuid5(NOTES_NAMESPACE, f"{note_id}:{index}:{deid_version}"))
        chunks.append(Chunk(chunk_index=index, text=piece, start=start, end=end, point_id=point_id))
        if end_i >= len(spans):
            break
        start_i = max(end_i - CHUNK_OVERLAP, start_i + 1)
        index += 1
    return chunks


def preserve_attack_passage(raw: str, sanitized: str) -> str:
    """Keep the evaluation attack block after identifier sanitization of the clinical prefix."""
    if ATTACK_MARK not in raw:
        return sanitized
    _, _, attack = raw.partition(ATTACK_MARK)
    if ATTACK_MARK in sanitized:
        return sanitized
    return f"{sanitized.rstrip()}\n\n{ATTACK_MARK}{attack}"


def hints_from_mapping(
    *,
    names: Iterable[str] = (),
    dob_strings: Iterable[str] = (),
    mrns: Iterable[str] = (),
    phones: Iterable[str] = (),
    source_ids: Iterable[str] = (),
) -> IdentityHints:
    return IdentityHints(
        names=tuple(n for n in names if n),
        dob_strings=tuple(d for d in dob_strings if d),
        mrns=tuple(m for m in mrns if m),
        phones=tuple(p for p in phones if p),
        source_ids=tuple(s for s in source_ids if s),
    )
