"""Input and output rails. Second wall, not the PDP."""

from __future__ import annotations

import re
from dataclasses import dataclass

IDENTITY_CLAIM = re.compile(
    r"\b(i am (dr|the attending|admin|the researcher)|as admin|ignore (the )?policy|system override)\b",
    re.I,
)
PATIENT_ID = re.compile(r"\bp_[0-9a-z]+\b")
NOTE_ID = re.compile(r"\b(?:note_[a-z0-9]+|p1\d{2}-[a-z0-9-]+|p_[0-9a-z]+-[a-z0-9-]+)\b", re.I)
_PATIENT_KEY_TOKEN = re.compile(r"\[?p_[0-9a-z]+(?:-[a-z0-9-]+)?\]?", re.I)
_CITE_ID_PAREN = re.compile(r"\(\s*cite_id:\s*[^)]+\)", re.I)
_CITE_ID_BRACKET = re.compile(r"\[cite_id:\s*([a-z0-9_-]+)\]", re.I)
REFUSAL = "No authorized evidence for that question."
NOT_ALLOWED = "This is not allowed."


@dataclass
class RailResult:
    ok: bool
    reason: str = ""
    text: str = ""


def input_rails(question: str) -> RailResult:
    if IDENTITY_CLAIM.search(question or ""):
        return RailResult(False, "identity_claim")
    return RailResult(True, text=question)


def scrub_internal_ids(answer: str, patient_key: str | None = None) -> str:
    """Remove patient keys and note filenames from a model answer before display."""
    text = answer or ""
    if patient_key:
        text = re.sub(rf"\[?{re.escape(patient_key)}(?:-[a-z0-9-]+)?\]?", "", text, flags=re.I)
    text = _PATIENT_KEY_TOKEN.sub("", text)
    text = re.sub(r"\bpatient_key\b", "", text, flags=re.I)
    text = _CITE_ID_BRACKET.sub(r"[\1]", text)
    text = _CITE_ID_PAREN.sub("", text)
    text = re.sub(r"`\s*`", "", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


def output_rails(answer: str, allowed_ids: set[str], *, patient_key: str | None = None) -> RailResult:
    text = scrub_internal_ids(answer, patient_key)
    found = set(PATIENT_ID.findall(text)) | set(NOTE_ID.findall(text))
    leaked = {i for i in found if i not in allowed_ids}
    if leaked:
        return RailResult(False, "citation_leak", REFUSAL)
    if not text:
        return RailResult(False, "empty", REFUSAL)
    return RailResult(True, text=text)
