"""Clinical projection of Synthea and demo rows for the Patient360 tools.

`clean_seed.py` removes survey/social-history observations and non-clinical
Synthea conditions from the store. These predicates keep /tools/query aligned
with that cleaned seed if a later ingest reintroduces noise.
"""

from __future__ import annotations

import re

# Display allowlist shared by the conditions dataset. Social/SDOH findings are
# stored as Condition resources by Synthea and must not appear as diagnoses.
CLINICAL_CONDITION_PATTERN = (
    r"diabetes|prediabetes|hypertension|pneumonia|hypoxemia|thrombosis|"
    r"coronavirus|covid|respiratory distress|kidney|asthma|depressive|"
    r"depression|hyperlipidemia|pregnancy prevention"
)
CLINICAL_CONDITION_WHERE = f"t.display ~* '{CLINICAL_CONDITION_PATTERN}'"
LAB_CLINICAL_CATEGORY_WHERE = "t.category IN ('laboratory', 'vital-signs')"


def clean_synthea_name(value: str | None) -> str:
    """Strip Synthea's trailing generator digits: Jerold208 -> Jerold."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", " ", value or "")).strip()


_SDOH_ITEM = re.compile(
    r"employment|labor force|medication review|social isolation|stress \(finding\)|"
    r"limited social|reports of violence|housing status|unemployed|received higher education|"
    r"has a high school|socioeconomic",
    re.I,
)
_SOCIAL_SENTENCE = re.compile(
    r"never smoked|identifies as|socioeconomic|college courses|high school education|"
    r"comes from a |patient is single|no complaints|\binsurance\b|humana|medicaid|medicare",
    re.I,
)
_SYNTHEA_NOTE = re.compile(
    r"the following procedures were conducted|the following lab reports were completed|"
    r"socioeconomic background|identifies as heterosexual|has never smoked|"
    r"the patient was prescribed the following medications",
    re.I,
)
_SPECIMEN_ONLY = re.compile(
    r"^(blood|blood by automated count|serum or plasma.*|platelet poor plasma.*)$",
    re.I,
)
_NOTE_LEFTOVER = re.compile(r"^(the patient was|the patient)$", re.I)
_HISTORY_NOISE = re.compile(
    r"^(cbc|cbc differential|cmp|iron panel|pt|high-sensitivity troponin i|"
    r"chest x-ray|oxygen by mask|prone positioning)$",
    re.I,
)
_ITEM_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"plain x-ray of chest", re.I), "chest x-ray"),
    (re.compile(r"oxygen administration by mask", re.I), "oxygen by mask"),
    (re.compile(r"placing subject in prone position", re.I), "prone positioning"),
    (re.compile(r"^cbc panel\b", re.I), "CBC"),
    (re.compile(r"auto differential panel", re.I), "CBC differential"),
    (re.compile(r"comprehensive metabolic 2000 panel", re.I), "CMP"),
    (re.compile(r"^iron panel\b", re.I), "iron panel"),
    (re.compile(r"troponin i\.cardiac", re.I), "high-sensitivity troponin I"),
    (re.compile(r"^pt panel\b", re.I), "PT"),
    (re.compile(r"0\.4 ml enoxaparin sodium 100 mg/ml prefilled syringe", re.I), "enoxaparin 40 mg"),
    (re.compile(r"acetaminophen 500 mg oral tablet", re.I), "acetaminophen 500 mg"),
    (re.compile(r"suspected disease caused by severe acute respiratory coronavirus 2", re.I), "suspected COVID-19"),
    (re.compile(r"disease caused by severe acute respiratory syndrome coronavirus 2", re.I), "COVID-19"),
    (re.compile(r"severe anxiety \(panic\)", re.I), "panic disorder"),
    (re.compile(r"disorder of teeth and/or supporting structures", re.I), "dental disease"),
)


def _note_slice(text: str, start: str, stops: tuple[str, ...]) -> str:
    match = re.search(start, text, re.I)
    if not match:
        return ""
    rest = text[match.end() :]
    ends = [found.start() for stop in stops if (found := re.search(stop, rest, re.I))]
    return rest[: min(ends)] if ends else rest


def _pretty_item(raw: str) -> str:
    item = re.split(r"\s+patient is presenting\b", raw, flags=re.I)[0]
    item = re.sub(r"\s*\((?:disorder|finding|situation|procedure)\)\s*$", "", item.strip(" .-"), flags=re.I)
    item = re.sub(
        r"\s*-\s*(blood by automated count|serum or plasma.*|platelet poor plasma.*)$",
        "",
        item,
        flags=re.I,
    )
    for pattern, label in _ITEM_ALIASES:
        if pattern.search(item):
            return label
    return re.sub(r"\s+", " ", item).strip(" .")


def _unique_items(blob: str, *, drop_history_noise: bool = False) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in re.split(r"\s+-\s+|,\s+", blob):
        item = _pretty_item(part)
        if not item or _SDOH_ITEM.search(item) or _SPECIMEN_ONLY.search(item) or _NOTE_LEFTOVER.search(item):
            continue
        if drop_history_noise and _HISTORY_NOISE.search(item):
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _drop_social_part(part: str) -> str:
    """Keep a clinical clause when it shares a sentence with Synthea social-history filler."""
    trimmed = part.strip()
    if not trimmed or not _SOCIAL_SENTENCE.search(trimmed):
        return trimmed
    kept = [
        clause.strip()
        for clause in re.split(r",\s+|\s+and\s+", trimmed, flags=re.I)
        if clause.strip() and not _SOCIAL_SENTENCE.search(clause)
    ]
    return ", ".join(kept)


def drop_social_sentences(text: str) -> str:
    """Drop Synthea template sentences about smoking, identity, class, school, and insurance."""
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n+", (text or "").strip()):
        sentences: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph.strip()):
            parts = [_drop_social_part(part) for part in re.split(r"\s+-\s+", sentence)]
            kept = " - ".join(part for part in parts if part)
            if kept:
                sentences.append(kept)
        if sentences:
            paragraphs.append(" ".join(sentences))
    return "\n".join(paragraphs).strip()


def clean_synthea_note(value: str | None) -> str:
    """Collapse Synthea template notes: drop SDOH filler and repeated lists."""
    text = re.sub(r"</?[A-Z]+>", " ", value or "")
    text = re.sub(r"^#+\s+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or not _SYNTHEA_NOTE.search(text):
        return drop_social_sentences((value or "").strip())
    lines: list[str] = []
    who = re.search(r"(\d+)\s*year-old\b.*?\b(male|female|other)\b", text, re.I)
    if who:
        lines.append(f"{who.group(1)}-year-old {who.group(2).lower()}.")
    presenting = _unique_items(
        _note_slice(
            text,
            r"presenting with",
            (r"the following", r"no known allerg", r"has never smoked", r"identifies as", r"social history", r"patient is single"),
        )
    )
    history = _unique_items(
        _note_slice(
            text,
            r"has a history of",
            (r"presenting with", r"the following", r"social history", r"lab reports were completed", r"procedures were conducted"),
        ),
        drop_history_noise=True,
    )
    procedures = _unique_items(
        _note_slice(text, r"procedures were conducted:", (r"lab reports were completed", r"prescribed the following", r"no known allerg"))
    )
    labs = _unique_items(
        _note_slice(text, r"lab reports were completed:", (r"the patient was", r"prescribed the following", r"no known allerg"))
    )
    meds = _unique_items(
        _note_slice(
            text,
            r"prescribed the following medications:",
            (r"no known allerg", r"allergies", r"patient is presenting", r"procedures were conducted", r"lab reports were completed"),
        )
    )
    if presenting:
        lines.append("Presenting: " + ", ".join(presenting) + ".")
    if history:
        lines.append("History: " + ", ".join(history) + ".")
    if procedures:
        lines.append("Procedures: " + ", ".join(procedures) + ".")
    if labs:
        lines.append("Labs: " + ", ".join(labs) + ".")
    if meds:
        lines.append("Medications: " + ", ".join(meds) + ".")
    if re.search(r"no known allerg", text, re.I):
        lines.append("Allergies: none known.")
    if lines:
        return "\n".join(lines)
    return drop_social_sentences(text)
