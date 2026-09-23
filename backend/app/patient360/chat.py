"""POST /chat: mint a run token and answer through a NemoClaw sandbox turn."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .audit import OUTCOME_SUCCESS, AuditEvent
from .auth import runtoken
from .auth.subject import Caller
from .clinical_view import clean_synthea_name, drop_social_sentences
from .deps import AppDeps
from .errors import Deny, NotFound
from .guardrails import NOT_ALLOWED, REFUSAL, RailResult
from .identity import identity_banner
from .nemo_rails import rails_for
from .openshell import ensure_sandbox, session_sandbox_status, try_openshell_turn
from .tools.notes import run_notes
from .tools.query import run_query
from .tools.schemas import NotesRequest, QueryFilters, QueryRequest
from .tools.stores import is_notes_listing

log = logging.getLogger(__name__)


def _ask_timings(**stages: float) -> None:
    parts = " ".join(f"{name}={seconds:.2f}s" for name, seconds in stages.items())
    log.info("ask timings %s", parts)

NEMOCLAW_UNAVAILABLE = "NemoClaw was unavailable. No substitute answer was used."
NAMED_PATIENT_MISMATCH = (
    "That question names someone other than the open chart, so it was blocked. "
    "Open that patient's chart, then ask again."
)
OTHER_PATIENTS = (
    "Ask answers only this open chart. "
    "Other patients on today's schedule are not in these records."
)

_NOTE_WORD = re.compile(r"\bnotes?\b", re.I)
_TOOL_MENTIONS = ("labs", "meds", "conditions", "encounters", "allergies", "diet", "notes", "imaging")
_TOOL_MENTION = re.compile(
    r"(?<![A-Za-z0-9_])/(" + "|".join(_TOOL_MENTIONS) + r")\b",
    re.I,
)
_SOURCE_TYPE = {
    "labs": "lab",
    "meds": "medication",
    "conditions": "condition",
    "encounters": "encounter",
}


def mentioned_tools(question: str) -> list[str]:
    found: list[str] = []
    for match in _TOOL_MENTION.finditer(question or ""):
        token = match.group(1).lower()
        if token not in found:
            found.append(token)
    return found


def wants_notes(question: str) -> bool:
    if is_notes_listing(question) or bool(_NOTE_WORD.search(question or "")):
        return True
    return "notes" in mentioned_tools(question)


_IDENTITY_QUESTION = re.compile(
    r"""
    (?:
        \bwho(?:'s|s|\s+is)\s+this(?:\s+(?:person|patient|one))?\b
        |
        \bwho(?:'s|s|\s+is)\s+the\s+patient\b
        |
        \bwhose\s+(?:chart|record)\s+is\s+this\b
        |
        \bidentify\s+(?:this|the)\s+(?:person|patient)\b
        |
        \bwho\s+am\s+i\s+looking\s+at\b
        |
        \bwhat(?:'s|\s+is)\s+(?:this|the)\s+patient'?s\s+name\b
    )
    """,
    re.I | re.X,
)
_CLINICAL_ASK = re.compile(
    r"\b(labs?|medications?|meds?|conditions?|notes?|visit|changed|summarize|cholesterol|pressure|hba1c|creatinine|prescribed?)\b",
    re.I,
)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def wants_identity(question: str) -> bool:
    """True when the question asks who the open chart is, not for a clinical brief."""
    text = question or ""
    if _CLINICAL_ASK.search(text):
        return False
    return bool(_IDENTITY_QUESTION.search(text))


_NEXT_APPOINTMENT = re.compile(
    r"""
    (?:
        \b(?:next|upcoming)\s+appointments?\b
        |
        \bwhen(?:'s|\s+is)\s+(?:my|the|this)\s+(?:next\s+)?appointments?\b
        |
        \bwhat\s+time\s+is\s+(?:my|the|this)\s+(?:next\s+)?appointments?\b
    )
    """,
    re.I | re.X,
)
_BOOKED_STATUS = frozenset({"booked", "pending"})


_VISTA_CATALOG = re.compile(
    r"""
    (?:
        \b(?:possible|available)\b.{0,80}\b(?:overlays?|segments?|classes?|labels?)\b
        |
        \bwhat\s+(?:are\s+)?(?:the\s+)?(?:possible|available)\b.{0,80}\b(?:overlay|segment|class|vista)
        |
        \bvista-?3d\b.{0,80}\b(?:possible|available|classes|labels|organs)\b
    )
    """,
    re.I | re.S | re.X,
)


def wants_vista_catalog(question: str) -> bool:
    """True when the question asks which VISTA classes exist, not to run one."""
    return bool(_VISTA_CATALOG.search(question or ""))


def wants_next_appointment(question: str) -> bool:
    """True when the question asks for this chart's next visit, not today's roster."""
    text = question or ""
    if asks_for_other_patients(text):
        return False
    return bool(_NEXT_APPOINTMENT.search(text))


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def next_appointment_row(rows: list[dict[str, Any]], *, now: datetime) -> dict[str, Any] | None:
    """Earliest booked or pending visit that has not already started."""
    moment = now if now.tzinfo else now.replace(tzinfo=UTC)
    upcoming: list[tuple[datetime, dict[str, Any]]] = []
    for row in rows:
        if row.get("redacted"):
            continue
        if str(row.get("status") or "").lower() not in _BOOKED_STATUS:
            continue
        at = _as_datetime(row.get("started_at"))
        if at is None or at < moment:
            continue
        upcoming.append((at, row))
    if not upcoming:
        return None
    upcoming.sort(key=lambda item: item[0])
    return upcoming[0][1]


def format_appointment_when(value: Any) -> str:
    at = _as_datetime(value)
    if at is None:
        return ""
    clock = f"{at.hour:02d}:{at.minute:02d}"
    return f"{at.day} {_MONTHS[at.month - 1]} {at.year} at {clock}"


def appointment_answer(row: dict[str, Any]) -> str:
    when = format_appointment_when(row.get("started_at"))
    dept = str(row.get("dept") or "").strip()
    reason = str(row.get("type_display") or row.get("reason_display") or "").strip()
    if reason and dept and reason.lower() == dept.lower():
        reason = ""
    parts = [part for part in (when, dept, reason) if part]
    fact = ", ".join(parts) if parts else "booked"
    cite = str(row.get("cite_id") or "").strip()
    cited = f" [{cite}]" if cite else ""
    return f"The next appointment is {fact}{cited}."


_OTHER_PATIENTS = re.compile(
    r"""
    (?:
        \bother\s+patients?\b
        |
        \bpatients?\s+do\s+i\s+have\b
        |
        \b(?:my|today'?s)\s+(?:patients?|roster|schedule|appointments)\b
        |
        \bwho\s+else\s+(?:do\s+i|is\s+on|am\s+i)\b
        |
        \b(?:list|show)\s+(?:me\s+)?(?:all|my|the|today'?s)\s+patients?\b
    )
    """,
    re.I | re.X,
)
_ROSTER_CLAIM = re.compile(
    r"\byou have\s+(?:one|two|three|four|five|\d+|an?|another|other)\s+patients?\b",
    re.I,
)


def asks_for_other_patients(question: str) -> bool:
    """True when the question wants a roster instead of this open chart."""
    return bool(_OTHER_PATIENTS.search(question or ""))


def claims_other_patients(answer: str) -> bool:
    """True when a draft treats one chart as a list of patients."""
    return bool(_ROSTER_CLAIM.search(answer or ""))


_CAP_NAME = r"[A-Z][A-Za-z']*\d*"
_NAMED_PATIENT = re.compile(
    rf"\b(?:patient|of|for|about)\s+({_CAP_NAME}(?:\s+{_CAP_NAME}){{1,4}})\b"
)


def named_patient(question: str) -> str | None:
    """A person named after patient/of/for/about. Ids such as patient 103 are not names."""
    match = _NAMED_PATIENT.search(question or "")
    if not match:
        return None
    return match.group(1)


def _name_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.findall(r"[a-z]+", clean_synthea_name(value).lower()) if len(token) > 1)


def name_matches(named: str, banner: dict[str, Any]) -> bool:
    asked = _name_tokens(named)
    full = _name_tokens(f"{banner.get('given_name') or ''} {banner.get('family_name') or ''}")
    if len(asked) < 2 or len(full) < 2:
        return False
    if asked[-1] != full[-1]:
        return False
    return all(token in full for token in asked)


async def bind_named_patient(
    deps: AppDeps, caller: Caller, req: ChatRequest, *, now: datetime
) -> tuple[ChatRequest, str | None]:
    """Block a question that names someone other than the open chart."""
    named = named_patient(req.question)
    if not named:
        return req, None
    if req.patient_key:
        try:
            open_chart = await identity_banner(deps, caller, req.patient_key, now=now)
        except (NotFound, Deny):
            open_chart = None
        else:
            if name_matches(named, open_chart.banner):
                return req, None
    return req, "named_patient_mismatch"


def format_banner_date(iso: str) -> str:
    try:
        year, month, day = iso.split("-")
        return f"{int(day)} {_MONTHS[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return iso


def age_years(iso: str, now: datetime) -> int | None:
    try:
        year, month, day = (int(part) for part in iso.split("-"))
    except ValueError:
        return None
    age = now.year - year
    if (now.month, now.day) < (month, day):
        age -= 1
    return age if age >= 0 else None


def identity_answer(banner: dict[str, Any], *, now: datetime) -> str:
    given = str(banner.get("given_name") or "").strip()
    family = str(banner.get("family_name") or "").strip()
    name = f"{given} {family}".strip() or "the open chart"
    lines = [f"This open chart is {name} [identity_banner]."]
    details: list[str] = []
    dob = str(banner.get("birth_date") or "").strip()
    age = age_years(dob, now) if dob else None
    if age is not None:
        details.append(f"{age} years")
    if dob:
        details.append(f"born {format_banner_date(dob)}")
    sex = str(banner.get("sex") or "").strip()
    if sex:
        details.append(sex)
    mrn = str(banner.get("mrn") or "").strip()
    if mrn:
        details.append(mrn)
    if details:
        lines.append(" · ".join(details) + " [identity_banner].")
    return "\n".join(lines)


def note_evidence_label(chunk: dict[str, Any], patient_key: str | None) -> str:
    typed = str(chunk.get("type_display") or "").strip()
    if typed:
        return typed
    note_id = str(chunk.get("note_id") or "")
    if re.search(r"admission", note_id, re.I):
        return "Admission note"
    if patient_key and note_id.startswith(f"{patient_key}-"):
        alias = note_id[len(patient_key) + 1 :].replace("-", " ").strip()
        return alias.title() if alias else "Clinical note"
    return note_id or "note"


_HISTORICAL_NOTE = re.compile(r"historical", re.I)


def is_historical_note(chunk: dict[str, Any], patient_key: str | None) -> bool:
    nid = str(chunk.get("note_id") or "")
    label = note_evidence_label(chunk, patient_key)
    return bool(_HISTORICAL_NOTE.search(nid) or _HISTORICAL_NOTE.search(label))


def note_evidence_text(chunk: dict[str, Any], patient_key: str | None) -> str:
    text = str(chunk.get("text") or "").strip()
    if text and is_historical_note(chunk, patient_key):
        return f"Past encounter, not a current condition. {text}"
    return text


def safe_note_cite(chunk: dict[str, Any], patient_key: str | None) -> str:
    """Token the model may cite. Never the patient-key note filename."""
    cite = str(chunk.get("cite_id") or "").strip()
    nid = str(chunk.get("note_id") or "").strip()
    if cite and not (patient_key and patient_key in cite):
        return cite
    if nid and patient_key and nid.startswith(f"{patient_key}-"):
        return "note_" + nid[len(patient_key) + 1 :].replace("-", "_")
    return cite or nid or "note"


def allow_note_handles(allowed_ids: set[str], row: dict[str, Any], patient_key: str | None) -> None:
    """Keep every cite handle this chart's notes tool returned. A patient-key filename is not one."""
    token = safe_note_cite(row, patient_key)
    if token and not (patient_key and patient_key in token):
        allowed_ids.add(token)
    cite = str(row.get("cite_id") or "").strip()
    if cite and not (patient_key and patient_key in cite):
        allowed_ids.add(cite)


def _citation(item: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(item["id"]),
        "label": str(item["label"]),
        "sourceId": str(item["sourceId"]),
        "sourceType": str(item["sourceType"]),
    }


_BRACKET_CITE = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]{2,})\]")
_LOINC_IN_LINE = re.compile(r"\b(\d{2,5}-\d)\b")


def _evidence_by_id(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        for key in ("sourceId", "id", "cite"):
            token = str(item.get(key) or "").strip()
            if token:
                by_id.setdefault(token, item)
    return by_id


def cited_evidence(answer: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evidence rows whose cite ids appear in the answer, in that order."""
    by_id = _evidence_by_id(evidence)
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _BRACKET_CITE.finditer(answer or ""):
        token = match.group(1)
        item = by_id.get(token)
        if item is None or token in seen:
            continue
        seen.add(token)
        chosen.append(item)
    return chosen


def citations_for(
    question: str, evidence: list[dict[str, Any]], answer: str = ""
) -> list[dict[str, str]]:
    cited = cited_evidence(answer, evidence)
    if cited:
        return [_citation(item) for item in cited[:16]]
    if wants_notes(question):
        notes = [item for item in evidence if item.get("sourceType") == "note"]
        other = [item for item in evidence if item.get("sourceType") != "note"]
        ordered = notes + other
    else:
        ordered = evidence
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in ordered:
        key = (str(item.get("sourceType") or ""), str(item.get("label") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return [_citation(item) for item in unique[:8]]


_QUESTION_LAB_CODES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"diabetes|hba1c|a1c|self-management|self management", re.I), "4548-4"),
    (re.compile(r"hypertension|blood pressure|lifestyle education", re.I), "8480-6"),
    (re.compile(r"hypertension|blood pressure|lifestyle education", re.I), "8462-4"),
    (re.compile(r"pneumonia|hypoxemia|oxygen|spo2|saturation", re.I), "2708-6"),
    (re.compile(r"pneumonia|respiratory distress|respiratory rate", re.I), "9279-1"),
)
_SUMMARY_QUESTION = re.compile(
    r"summarize|visible record|last visit|what changed|overview|clinical brief|latest labs",
    re.I,
)
_SNAPSHOT_QUESTION = re.compile(
    r"last visit|what changed|visible record|clinical brief|overview|since the last",
    re.I,
)
_SNAPSHOT_LAB_CODES: tuple[str, ...] = (
    "4548-4",
    "8480-6",
    "8462-4",
    "2708-6",
    "9279-1",
    "2160-0",
)
_PANEL_NOISE = re.compile(
    r"carbon dioxide|body weight|^weight\b|body mass|chloride|^urea nitrogen|hematocrit",
    re.I,
)


def extra_lab_codes(question: str) -> list[str]:
    """Structured codes the question is asking about, in addition to latest labs."""
    seen: list[str] = []
    for pattern, code in _QUESTION_LAB_CODES:
        if pattern.search(question) and code not in seen:
            seen.append(code)
    if _SUMMARY_QUESTION.search(question or ""):
        for code in _SNAPSHOT_LAB_CODES:
            if code not in seen:
                seen.append(code)
    return seen


def is_panel_noise(label: str) -> bool:
    """CMP/vitals leftovers that crowd out disease-relevant measurements."""
    return bool(_PANEL_NOISE.search(label or ""))


def wants_latest_snapshot(question: str) -> bool:
    """True when the clinician wants the current picture, not a historical series."""
    return bool(_SNAPSHOT_QUESTION.search(question or ""))


_LAB_LABELS = (
    (re.compile(r"hemoglobin a1c", re.I), "HbA1c"),
    (re.compile(r"^creatinine\b", re.I), "Creatinine"),
    (re.compile(r"^potassium\b", re.I), "Potassium"),
    (re.compile(r"glomerular filtration", re.I), "eGFR"),
    (re.compile(r"^systolic blood pressure", re.I), "Systolic BP"),
    (re.compile(r"^diastolic blood pressure", re.I), "Diastolic BP"),
    (re.compile(r"blood pressure panel", re.I), ""),
    (re.compile(r"^cholesterol\b", re.I), "Cholesterol"),
    (re.compile(r"leukocytes|^wbc\b", re.I), "WBC"),
    (re.compile(r"^hemoglobin \[mass", re.I), "Hemoglobin"),
    (re.compile(r"^eosinophils\b", re.I), "Eosinophils"),
    (re.compile(r"oxygen saturation", re.I), "Oxygen saturation"),
    (re.compile(r"respiratory rate", re.I), "Respiratory rate"),
    (re.compile(r"^heart rate\b", re.I), "Heart rate"),
)


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _pretty_unit(unit: str) -> str:
    return (
        unit.replace("mm[Hg]", "mmHg")
        .replace("mL/min/{1.73_m2}", "mL/min/1.73m²")
        .replace("10*3/uL", "×10³/µL")
    )


_FULLWIDTH_CITE = re.compile(r"【\s*([A-Za-z][A-Za-z0-9_-]{2,})\s*】")
_BACKTICK_CITE = re.compile(
    r"`cite_id`\s*`([A-Za-z][A-Za-z0-9_-]{2,})`",
    re.I,
)
_LOOSE_CITE_ID = re.compile(
    r"`?cite_id`?\s+`?((?:obs|note|cond|med|enc|apt)_[A-Za-z0-9_-]+)`?",
    re.I,
)
_CITE_COLON = re.compile(
    r"\[cite:\s*((?:obs|note|cond|med|enc|apt)_[A-Za-z0-9_-]+)\]",
    re.I,
)
_OBS_BRACKET = re.compile(r"\[(obs_[A-Za-z0-9_-]+)\]", re.I)


def normalize_citations(text: str) -> str:
    """Turn model citation marks into the [cite_id] form the chart matches."""
    normalized = _FULLWIDTH_CITE.sub(r"[\1]", text or "")
    normalized = _BACKTICK_CITE.sub(r"[\1]", normalized)
    normalized = _LOOSE_CITE_ID.sub(r"[\1]", normalized)
    return _CITE_COLON.sub(r"[\1]", normalized)


def retarget_line_cites(answer: str, evidence: list[dict[str, Any]]) -> str:
    """Point a line's obs cite at the row for the LOINC code written on that line."""
    by_code: dict[str, str] = {}
    for item in evidence:
        code = str(item.get("code") or "").strip()
        cite = str(item.get("sourceId") or item.get("cite") or "").strip()
        if code and cite:
            by_code.setdefault(code, cite)
    if not by_code:
        return answer
    lines: list[str] = []
    for line in (answer or "").split("\n"):
        target = next((by_code[code] for code in _LOINC_IN_LINE.findall(line) if code in by_code), "")
        if target:
            line = _OBS_BRACKET.sub(lambda _match, cite=target: f"[{cite}]", line, count=1)
        lines.append(line)
    return "\n".join(lines)


def _usable_model_answer(text: str | None) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if low == "/approve" or "couldn't generate a response" in low:
        return False
    if low.startswith("llm request failed"):
        return False
    return True


def evidence_label(row: dict[str, Any], dataset: str) -> str:
    raw = str(row.get("display") or row.get("code") or dataset)
    if dataset != "labs":
        return raw
    for pattern, label in _LAB_LABELS:
        if pattern.search(raw):
            return label
    shortened = re.sub(r"\s*\[[^\]]+\]", "", raw).split(" in ")[0].strip()
    return shortened or raw


def evidence_text(row: dict[str, Any], dataset: str) -> str:
    """Value side of a cited fact. Never fall back to the display name."""
    if dataset == "labs":
        keys = ("value_num", "value_text", "value_display", "value_code")
        value = next((row[key] for key in keys if _present(row.get(key))), None)
        if value is None and row.get("value_bool") is not None:
            value = row["value_bool"]
        if value is None:
            return ""
        unit = _pretty_unit(str(row.get("unit") or ""))
        return f"{value} {unit}".strip()
    if dataset == "conditions":
        parts: list[str] = []
        for key in ("clinical_status", "verification_status"):
            if _present(row.get(key)):
                parts.append(str(row[key]))
        if _present(row.get("onset_date")):
            parts.append(f"onset {row['onset_date']}")
        if parts:
            return ", ".join(parts)
        # A named condition is still a citable row when status and onset are blank.
        return "recorded" if _present(row.get("display")) else ""
    if dataset == "meds":
        if _present(row.get("dosage_text")):
            text = str(row["dosage_text"])
        elif _present(row.get("dose_value")):
            text = f"{row['dose_value']} {row.get('dose_unit') or ''}".strip()
        else:
            text = ""
        if _present(row.get("status")):
            text = f"{text}, {row['status']}".strip(", ") if text else str(row["status"])
        return text
    if dataset == "encounters":
        parts = []
        if _present(row.get("started_at")):
            parts.append(str(row["started_at"])[:10])
        if _present(row.get("reason_display") or row.get("type_display")):
            parts.append(str(row.get("reason_display") or row.get("type_display")))
        if _present(row.get("status")):
            parts.append(str(row["status"]))
        return ", ".join(parts)
    return ""


_HISTORY_LIMIT = 8
_HISTORY_CHARS = 2000


class ChatMessage(BaseModel):
    """One prior turn. Extra keys are rejected so a history item cannot carry evidence."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=_HISTORY_CHARS)

    @field_validator("content", mode="before")
    @classmethod
    def clip_content(cls, value: object) -> str:
        return str(value or "").strip()[:_HISTORY_CHARS]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=2000)
    patient_key: str | None = Field(None, pattern=r"^p_[0-9a-z]+$", max_length=64)
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("history", mode="before")
    @classmethod
    def cap_history(cls, value: object) -> object:
        if isinstance(value, list) and len(value) > _HISTORY_LIMIT:
            return value[-_HISTORY_LIMIT:]
        return value


def _blocked_answer(result: RailResult) -> str:
    if result.reason == "content_safety":
        return NOT_ALLOWED
    return REFUSAL


def _chat_result(
    *,
    answer: str,
    citations: list[dict[str, str]],
    steps: list[str],
    audit_id: str,
    reason: str | None,
    refused: bool,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "citations": citations,
        "retrievalSteps": steps,
        "audit_id": audit_id,
        "policy_reason": reason,
        "refused": refused,
    }


async def _identity_chat(deps: AppDeps, caller: Caller, req: ChatRequest, *, now: datetime) -> dict[str, Any]:
    """Answer who-is questions from the dashboard identity banner. No agent, no clinical dump."""
    evidence: list[dict[str, Any]] = []
    allowed_ids: set[str] = set()
    steps = ["Read authorized identity banner"]
    answer = REFUSAL
    refused = True
    reason: str | None = "no_authorized_evidence"
    if req.patient_key:
        try:
            result = await identity_banner(deps, caller, req.patient_key, now=now)
        except (NotFound, Deny):
            steps = ["Identity banner not authorized"]
        else:
            answer = identity_answer(result.banner, now=now)
            refused = False
            reason = None
            allowed_ids.add("identity_banner")
            evidence.append(
                {
                    "id": "identity_banner",
                    "cite": "identity_banner",
                    "label": "Identity banner",
                    "sourceId": "identity_banner",
                    "sourceType": "identity",
                    "text": answer,
                }
            )
    else:
        steps = ["Identity banner not authorized"]
    out = await rails_for(deps).check_output(
        answer, allowed_ids, patient_key=req.patient_key, question=req.question
    )
    if not out.ok:
        answer, refused, reason = _blocked_answer(out), True, out.reason
    else:
        answer = out.text
    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=caller.user.user_id,
            agent_software="patient360-identity_banner",
            purpose_of_event="TREAT",
            entity_patient=req.patient_key,
            entity_resource="chat",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="chat_answered",
            session_id=caller.sid,
            detail={"refused": refused, "reason": reason, "runtime": "identity_banner"},
        )
    )
    return _chat_result(
        answer=answer,
        citations=citations_for(req.question, evidence),
        steps=steps,
        audit_id=str(audit_id),
        reason=reason,
        refused=refused,
    )


async def _appointment_chat(deps: AppDeps, caller: Caller, req: ChatRequest, *, now: datetime) -> dict[str, Any]:
    """Answer from booked visits on this chart. No agent, and no other patients' slots."""
    evidence: list[dict[str, Any]] = []
    allowed_ids: set[str] = set()
    steps = ["Appointments not authorized"]
    answer = REFUSAL
    refused = True
    reason: str | None = "no_authorized_evidence"
    if req.patient_key:
        try:
            found = await run_query(
                deps,
                caller,
                QueryRequest(
                    patient_key=req.patient_key,
                    dataset="encounters",
                    filters=QueryFilters(limit=200),
                ),
                now=now,
            )
        except (NotFound, Deny):
            found = None
        else:
            steps = ["Searched authorized appointments"]
            row = next_appointment_row(list(found.rows), now=now)
            if row is not None:
                answer = appointment_answer(row)
                refused = False
                reason = None
                cite = str(row.get("cite_id") or "")
                if cite:
                    allowed_ids.add(cite)
                label = str(row.get("type_display") or row.get("dept") or "Appointment")
                evidence.append(
                    {
                        "id": cite or str(uuid4()),
                        "cite": cite,
                        "label": label,
                        "sourceId": cite,
                        "sourceType": "encounter",
                        "text": answer,
                    }
                )
    out = await rails_for(deps).check_output(
        answer, allowed_ids, patient_key=req.patient_key, question=req.question
    )
    if not out.ok:
        answer, refused, reason = _blocked_answer(out), True, out.reason
    else:
        answer = out.text
    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=caller.user.user_id,
            agent_software="patient360-appointment",
            purpose_of_event="TREAT",
            entity_patient=req.patient_key,
            entity_resource="chat",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="chat_answered",
            session_id=caller.sid,
            detail={"refused": refused, "reason": reason, "runtime": "appointment"},
        )
    )
    return _chat_result(
        answer=answer,
        citations=citations_for(req.question, evidence),
        steps=steps,
        audit_id=str(audit_id),
        reason=reason,
        refused=refused,
    )


async def run_chat(deps: AppDeps, caller: Caller, req: ChatRequest, *, now: datetime) -> dict[str, Any]:
    started = perf_counter()
    mark = started
    rails = await rails_for(deps).check_input(req.question)
    input_rail = perf_counter() - mark
    if not rails.ok:
        return {
            "answer": _blocked_answer(rails),
            "citations": [],
            "retrievalSteps": ["Input rail blocked the question"],
            "audit_id": str(uuid4()),
            "policy_reason": rails.reason,
            "refused": True,
        }

    if asks_for_other_patients(req.question):
        audit_id = await deps.audit.write(
            AuditEvent(
                event_type="tool_call",
                agent_user=caller.user.user_id,
                agent_software="patient360-other-patients",
                purpose_of_event="TREAT",
                entity_patient=req.patient_key,
                entity_resource="chat",
                outcome=OUTCOME_SUCCESS,
                outcome_desc="chat_answered",
                session_id=caller.sid,
                detail={"refused": True, "reason": "other_patients", "runtime": "other_patients"},
            )
        )
        return _chat_result(
            answer=OTHER_PATIENTS,
            citations=[],
            steps=["Question asks for other patients"],
            audit_id=str(audit_id),
            reason="other_patients",
            refused=True,
        )

    if wants_identity(req.question):
        return await _identity_chat(deps, caller, req, now=now)

    req, mismatch = await bind_named_patient(deps, caller, req, now=now)
    if mismatch:
        audit_id = await deps.audit.write(
            AuditEvent(
                event_type="tool_call",
                agent_user=caller.user.user_id,
                agent_software="patient360-named-patient",
                purpose_of_event="TREAT",
                entity_patient=req.patient_key,
                entity_resource="chat",
                outcome=OUTCOME_SUCCESS,
                outcome_desc="chat_answered",
                session_id=caller.sid,
                detail={"refused": True, "reason": mismatch, "runtime": "named_patient"},
            )
        )
        return _chat_result(
            answer=NAMED_PATIENT_MISMATCH,
            citations=[],
            steps=["Question names a different patient"],
            audit_id=str(audit_id),
            reason=mismatch,
            refused=True,
        )

    if wants_next_appointment(req.question):
        return await _appointment_chat(deps, caller, req, now=now)

    run_token, claims = runtoken.mint(
        deps.settings, user_id=caller.user.user_id, sid=caller.sid, agent_id="agent:openshell", now=now
    )
    agent = Caller(
        subject=caller.subject,
        channel="agent",
        session=caller.session,
        user=caller.user,
        jti=claims.jti,
        agent=claims.act_sub,
    )

    steps = ["Minted run token"]
    evidence: list[dict[str, Any]] = []
    allowed_ids: set[str] = set()
    listing_notes = is_notes_listing(req.question)
    snapshot = wants_latest_snapshot(req.question)
    labs_focus = "labs" in mentioned_tools(req.question)
    mark = perf_counter()
    if req.patient_key:
        if not listing_notes:
            extras = extra_lab_codes(req.question)
            # Question-matched codes first so latest generic labs cannot crowd out the asked-for measurements.
            queries: list[tuple[str, QueryFilters]] = [
                ("labs", QueryFilters(limit=32, code=code)) for code in extras
            ]
            if snapshot:
                queries.extend(
                    (dataset, QueryFilters(limit=32 if dataset == "conditions" else 8))
                    for dataset in ("encounters", "conditions", "meds")
                )
            else:
                queries.extend(
                    (dataset, QueryFilters(limit=32 if dataset in ("labs", "conditions") else 8))
                    for dataset in ("labs", "conditions", "meds")
                )
            seen_cites: set[str] = set()
            seen_lab_labels: set[str] = set()
            per_dataset = {"labs": 0, "conditions": 0, "meds": 0, "encounters": 0}
            steps.append("Searched authorized structured rows")
            for dataset, filters in queries:
                try:
                    q = await run_query(
                        deps,
                        agent,
                        QueryRequest(patient_key=req.patient_key, dataset=dataset, filters=filters),
                        now=now,
                    )
                except (NotFound, Deny):
                    continue
                if dataset == "labs" and labs_focus:
                    cap = 32
                elif dataset == "labs":
                    cap = 8
                elif dataset == "conditions":
                    cap = 16
                else:
                    cap = 4
                per_query = 1 if dataset == "labs" and filters.code else cap
                rows = list(q.rows)
                if dataset == "conditions" and snapshot:
                    active = [
                        row for row in rows if str(row.get("clinical_status") or "active").lower() == "active"
                    ]
                    rows = active or rows
                added = 0
                for row in rows:
                    if row.get("redacted") or per_dataset[dataset] >= cap or added >= per_query:
                        continue
                    text = evidence_text(row, dataset)
                    label = evidence_label(row, dataset)
                    if not text or not label:
                        continue
                    if dataset == "labs" and is_panel_noise(label) and not labs_focus:
                        continue
                    if dataset == "labs" and label.lower() in seen_lab_labels:
                        continue
                    cite = str(row.get("cite_id") or "")
                    if cite and cite in seen_cites:
                        continue
                    if cite:
                        seen_cites.add(cite)
                        allowed_ids.add(cite)
                    if dataset == "labs":
                        seen_lab_labels.add(label.lower())
                    evidence.append(
                        {
                            "id": cite or str(uuid4()),
                            "cite": cite,
                            "label": label,
                            "sourceId": cite,
                            "sourceType": _SOURCE_TYPE.get(dataset, "note"),
                            "text": text,
                            "code": str(row.get("code") or ""),
                        }
                    )
                    per_dataset[dataset] += 1
                    added += 1
        try:
            notes = await run_notes(
                deps, agent, NotesRequest(patient_key=req.patient_key, question=req.question), now=now
            )
            steps.append("Searched authorized notes")
            for row in list(notes.notes) + list(notes.chunks):
                allow_note_handles(allowed_ids, row, req.patient_key)
            source_rows = list(notes.notes if listing_notes and notes.notes else notes.chunks)
            if (
                snapshot
                and not wants_notes(req.question)
                and not re.search(r"visit|changed", req.question or "", re.I)
            ):
                source_rows = []
            elif snapshot:
                source_rows = list(notes.notes)[:1] or source_rows[:1]
            note_items: list[dict[str, Any]] = []
            for chunk in source_rows:
                nid = str(chunk.get("note_id") or chunk.get("cite_id") or "")
                highlight = str(chunk.get("cite_id") or nid)
                citation_token = safe_note_cite(chunk, req.patient_key)
                allowed_ids.add(citation_token)
                if highlight and not (req.patient_key and req.patient_key in highlight):
                    allowed_ids.add(highlight)
                note_items.append(
                    {
                        "id": citation_token,
                        "cite": citation_token,
                        "label": note_evidence_label(chunk, req.patient_key),
                        "sourceId": highlight,
                        "sourceType": "note",
                        "text": note_evidence_text(chunk, req.patient_key),
                    }
                )
            evidence = note_items + evidence if wants_notes(req.question) else evidence + note_items
        except (NotFound, Deny):
            steps.append("Notes not authorized")
    prefetch = perf_counter() - mark

    runtime = "openshell"
    sandbox = caller.session.sandbox_id
    mark = perf_counter()
    if deps.settings.openshell_url:
        try:
            provisioned = await ensure_sandbox(
                deps.settings.openshell_url, caller.sid, sandbox=sandbox
            )
            if provisioned:
                try:
                    prior = caller.session.sandbox_id
                    sandbox = await deps.manager.bind_sandbox(caller.session, provisioned)
                    if not prior:
                        steps.append("Bound OpenShell sandbox")
                except Exception:
                    sandbox = provisioned
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            log.warning("NemoClaw sandbox setup failed: %s (HTTP %s)", type(exc).__name__, status)
            steps.append("NemoClaw sandbox setup failed")
            sandbox = caller.session.sandbox_id or sandbox
    sandbox_ensure = perf_counter() - mark
    mark = perf_counter()
    generated = await try_openshell_turn(
        deps.settings,
        run_token,
        req.question,
        sandbox=sandbox or "",
        patient_key=req.patient_key,
        history=[{"role": item.role, "content": item.content} for item in req.history],
    )
    turn = perf_counter() - mark
    if _usable_model_answer(generated) and claims_other_patients(generated or ""):
        steps.append("Question asks for other patients")
        answer, refused, reason = OTHER_PATIENTS, True, "other_patients"
        evidence = []
    elif _usable_model_answer(generated):
        steps.append("OpenShell sandbox turn")
        answer = retarget_line_cites(normalize_citations(generated or ""), evidence)
        refused, reason = False, None
    else:
        steps.append("NemoClaw unavailable")
        answer, refused, reason = NEMOCLAW_UNAVAILABLE, True, "nemoclaw_unavailable"
    mark = perf_counter()
    out = await rails_for(deps).check_output(
        answer,
        {i for i in allowed_ids if i},
        patient_key=req.patient_key,
        question=req.question,
    )
    if not out.ok:
        answer, refused, reason = _blocked_answer(out), True, out.reason
    else:
        answer = drop_social_sentences(out.text)
        if not answer:
            answer, refused, reason = REFUSAL, True, "no_authorized_evidence"
    output_rail = perf_counter() - mark
    _ask_timings(
        input_rail=input_rail,
        prefetch=prefetch,
        sandbox_ensure=sandbox_ensure,
        turn=turn,
        output_rail=output_rail,
        total=perf_counter() - started,
    )

    audit_id = await deps.audit.write(
        AuditEvent(
            event_type="tool_call",
            agent_user=caller.user.user_id,
            agent_software=f"patient360-{runtime}",
            purpose_of_event="TREAT",
            entity_patient=req.patient_key,
            entity_resource="chat",
            outcome=OUTCOME_SUCCESS,
            outcome_desc="chat_answered",
            session_id=caller.sid,
            jti=claims.jti,
            detail={"refused": refused, "reason": reason, "runtime": runtime},
        )
    )
    result: dict[str, Any] = {
        "answer": answer,
        "citations": citations_for(req.question, evidence, answer),
        "retrievalSteps": steps,
        "audit_id": str(audit_id),
        "policy_reason": reason,
        "refused": refused,
    }
    status = await session_sandbox_status(deps.settings, caller.session.sandbox_id or sandbox)
    if status.get("stamp"):
        result["sandbox_stamp"] = status["stamp"]
    return result
