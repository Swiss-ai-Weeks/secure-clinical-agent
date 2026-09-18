"""Input and output rails. Second wall, not the PDP."""

from __future__ import annotations

import re
from dataclasses import dataclass

IDENTITY_CLAIM = re.compile(
    r"\b(i am (dr|the attending|admin|the researcher)|as admin|ignore (the )?policy|system override)\b",
    re.I,
)
PATIENT_ID = re.compile(r"\bp_[0-9a-z]+\b")
NOTE_ID = re.compile(r"\b(?:note_[a-z0-9]+|p1\d{2}-[a-z0-9-]+)\b", re.I)
REFUSAL = "No authorized evidence for that question."


@dataclass
class RailResult:
    ok: bool
    reason: str = ""
    text: str = ""


def input_rails(question: str) -> RailResult:
    if IDENTITY_CLAIM.search(question or ""):
        return RailResult(False, "identity_claim")
    return RailResult(True, text=question)


def output_rails(answer: str, allowed_ids: set[str]) -> RailResult:
    found = set(PATIENT_ID.findall(answer)) | set(NOTE_ID.findall(answer))
    leaked = {i for i in found if i not in allowed_ids}
    if leaked:
        return RailResult(False, "citation_leak", REFUSAL)
    if not answer.strip():
        return RailResult(False, "empty", REFUSAL)
    return RailResult(True, text=answer)
