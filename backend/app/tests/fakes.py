"""In-memory stand-ins for Postgres, OpenFGA, and the vault.

The FGA fake holds the demo *tuples* with their windows and projects model.fga's
permissions over them (the model itself is tested by `fga model test`), so the
PDP, the endpoints, and tuple writes can be exercised offline. Windows here are
test data: wide where the demo needs them live, expired where tuples.demo.yaml
says expired.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from patient360.audit import AuditEvent
from patient360.auth.sessions import Session, User
from patient360.fga import Tuple, TupleExists, TupleMissing, Window
from patient360.pdp.models import Obligations
from patient360.tools.schemas import QueryFilters
from patient360.vault import Identity

# Build Plan §9 personas.
USERS: dict[str, User] = {
    "u_chen": User("u_chen", "attending", "internal-medicine", 3, True),
    "u_rivera": User("u_rivera", "care_team", "ward-3b", 2, True),
    "u_okafor": User("u_okafor", "consultant", "cardiology", 3, True),
    "u_nair": User("u_nair", "researcher", "research", 2, True),
    "u_maria": User("u_maria", "patient", None, 1, True),
    "u_diego": User("u_diego", "caregiver", None, 1, True),
    "u_lindqvist": User("u_lindqvist", "dietary_staff", "kitchen", 1, True),
    "u_haller": User("u_haller", "caregiver", None, 1, True),  # legal guardian of p_104
    "u_audit": User("u_audit", "auditor", "compliance", 3, True),
}


def _w(start: str, expiry: str) -> Window:
    return Window(
        datetime.fromisoformat(start).replace(tzinfo=UTC), datetime.fromisoformat(expiry).replace(tzinfo=UTC)
    )


# tuples.demo.yaml, with live windows widened so endpoint tests using the wall clock stay stable.
DEMO_TUPLES: list[Tuple] = [
    Tuple("user:u_chen", "attending", "patient:p_101", _w("2026-09-01", "2027-09-01")),
    Tuple("user:u_chen", "attending", "patient:p_102", _w("2026-09-01", "2027-09-01")),
    Tuple("user:u_rivera", "care_team", "patient:p_101", _w("2026-09-15", "2027-09-22")),
    Tuple("user:u_okafor", "consultant", "patient:p_101", _w("2026-09-17", "2027-09-27")),
    Tuple("user:u_okafor", "consultant", "patient:p_102", _w("2026-08-01", "2026-08-15")),  # expired
    Tuple("user:u_diego", "caregiver", "patient:p_103", _w("2026-06-01", "2027-12-01")),
    Tuple("user:u_diego", "caregiver_notes", "patient:p_103", _w("2026-03-01", "2026-06-01")),  # expired
    Tuple("user:u_nair", "researcher", "project:cohort_2026", _w("2026-01-01", "2027-01-01")),
    Tuple("user:u_lindqvist", "staff", "ward:w_3b", _w("2026-09-15", "2027-09-25")),
    Tuple("ward:w_3b", "admitted_to", "patient:p_101", _w("2026-09-10", "2027-10-10")),
    Tuple(
        "user:u_haller", "guardian", "patient:p_104", _w("2026-01-01", "2030-05-03")
    ),  # Lea's 18th birthday
]

# model.fga projected: permission -> direct relations that grant it (each "but not blocked").
PERMISSION_RELATIONS: dict[str, frozenset[str]] = {
    "can_read_clinical": frozenset(
        {"attending", "consultant", "care_team", "caregiver", "guardian", "emergency"}
    ),
    "can_read_notes": frozenset(
        {"attending", "consultant", "care_team", "caregiver_notes", "guardian", "emergency"}
    ),
    "can_read_imaging_metadata": frozenset({"attending", "consultant", "care_team", "guardian", "emergency"}),
    "can_read_imaging_report": frozenset({"attending", "consultant", "emergency"}),
    "can_view_pixels": frozenset({"attending", "consultant", "emergency"}),
    "can_read_diet": frozenset(
        {"attending", "care_team", "caregiver", "guardian", "emergency"}
    ),  # + staff from admitted_to
    "can_schedule": frozenset({"attending", "care_team", "caregiver", "guardian"}),
    "can_delegate": frozenset({"attending"}),
    "can_consent": frozenset({"guardian"}),
    "can_query_aggregate": frozenset({"researcher"}),
}

VAULT = {"u_maria": "p_103"}

# Synthetic identity records as the seed writes them to the vault. Only banner() may leave the backend.
IDENTITIES: dict[str, Identity] = {
    "p_101": Identity(
        "p_101",
        "Elisabeth",
        "Keller",
        "1961-04-17",
        "female",
        mrn="MRN-4471902",
        address={"line": "Seestrasse 14", "postal_code": "8002", "city": "Zürich", "country": "CH"},
        phone="+41 44 555 01 17",
        national_id="756.1234.5678.97",
    ),
    "p_102": Identity(
        "p_102",
        "Marco",
        "Bianchi",
        "1974-11-02",
        "male",
        mrn="MRN-4471903",
        address={"line": "Via Nassa 5", "postal_code": "6900", "city": "Lugano", "country": "CH"},
        phone="+41 91 555 02 02",
        national_id="756.2345.6789.08",
    ),
    "p_103": Identity(
        "p_103",
        "Maria",
        "Santos",
        "1958-07-23",
        "female",
        mrn="MRN-4471904",
        address={"line": "Rue du Rhône 8", "postal_code": "1204", "city": "Genève", "country": "CH"},
        phone="+41 22 555 03 23",
        national_id="756.3456.7890.19",
    ),
    "p_205": Identity(
        "p_205",
        "Jonas",
        "Weber",
        "1989-02-09",
        "male",
        mrn="MRN-4472051",
        address={"line": "Bundesplatz 3", "postal_code": "3011", "city": "Bern", "country": "CH"},
        phone="+41 31 555 05 09",
        national_id="756.4567.8901.20",
    ),
    "p_104": Identity(
        "p_104",
        "Lea",
        "Haller",
        "2012-05-03",
        "female",
        mrn="MRN-4471905",
        address={"line": "Hardturmstrasse 22", "postal_code": "8005", "city": "Zürich", "country": "CH"},
        phone="+41 44 555 04 03",
        national_id="756.5678.9012.31",
    ),
}
PII_ONLY_FIELDS = ("address", "phone", "national_id")


def seed_demo_consents(audit: FakeAudit) -> dict[tuple[str, str, str], UUID]:
    """Mirror seed_demo.py: a consent_granted row (detail.seeded = true) per demo grant tuple.

    Patient-side grants (p_103) are recorded as Maria's; staff assignments have no
    agent_user (the worker wrote them).
    """
    from patient360.fga import rfc3339

    ids: dict[tuple[str, str, str], UUID] = {}
    for t in DEMO_TUPLES:
        if not t.object.startswith("patient:") or t.relation in ("admitted_to", "emergency", "blocked"):
            continue
        grantee = t.user.removeprefix("user:")
        patient = t.object.removeprefix("patient:")
        granted_by = "u_maria" if patient == "p_103" else None
        assert t.window is not None
        ev = AuditEvent(
            event_type="consent_granted",
            agent_user=granted_by,
            agent_software="seed_demo",
            purpose_of_event="PATRQT" if granted_by else "HOPERAT",
            entity_patient=patient,
            entity_resource=f"consent/{t.relation}/{grantee}",
            detail={
                "relation": t.relation,
                "grantee": grantee,
                "granted_by": granted_by,
                "kind": "guardianship" if t.relation == "guardian" else "consent",
                "basis": "self_match"
                if granted_by
                else ("registration" if t.relation == "guardian" else "seed"),
                "start": rfc3339(t.window.start),
                "expiry": rfc3339(t.window.expiry),
                "justification": None,
                "tuple": t.as_dict(),
                "seeded": True,
            },
        )
        aid = uuid4()
        audit.events.append((aid, ev))
        audit.recorded[aid] = datetime.now(UTC)
        ids[t.key] = aid
    return ids


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[UUID, AuditEvent]] = []
        self.recorded: dict[UUID, datetime] = {}
        self.fail = False
        self.fail_types: set[str] = set()  # fail only these event types (e.g. consent_granted)
        self.fail_once_types: set[str] = set()  # fail the first write of these types, then succeed
        self.clock: datetime | None = None
        self.aggregates: list[dict[str, Any]] = []

    async def write(self, event: AuditEvent) -> UUID:
        from patient360.errors import Transient

        if self.fail or event.event_type in self.fail_types:
            raise Transient("audit down")
        if event.event_type in self.fail_once_types:
            self.fail_once_types.discard(event.event_type)
            raise Transient("audit down once")
        audit_id = uuid4()
        self.events.append((audit_id, event))
        self.recorded[audit_id] = self.clock or datetime.now(UTC)
        return audit_id

    def _row(self, aid: UUID, ev: AuditEvent) -> dict[str, Any]:
        return {
            "id": str(aid),
            "recorded_at": (self.recorded.get(aid) or datetime.now(UTC)).isoformat(),
            "event_type": ev.event_type,
            "agent_user": ev.agent_user,
            "agent_software": ev.agent_software,
            "purpose_of_event": ev.purpose_of_event,
            "entity_patient": ev.entity_patient,
            "entity_resource": ev.entity_resource,
            "outcome": ev.outcome,
            "reason_code": ev.reason_code,
            "policy_version": ev.policy_version,
            "session_id": ev.session_id,
            "detail": ev.detail,
        }

    async def get(self, audit_id: UUID) -> dict[str, Any] | None:
        for aid, ev in self.events:
            if aid == audit_id:
                row = self._row(aid, ev)
                row["id"] = str(aid)
                return row
        return None

    async def get_consent(self, consent_id: UUID) -> dict[str, Any] | None:
        for aid, ev in self.events:
            if aid == consent_id and ev.event_type == "consent_granted":
                return self._row(aid, ev)
        return None

    async def consent_events(self, patient_key: str) -> list[dict[str, Any]]:
        return [
            self._row(aid, ev)
            for aid, ev in self.events
            if ev.entity_patient == patient_key and ev.event_type in ("consent_granted", "consent_revoked")
        ]

    async def active_break_glass(
        self, user_id: str, patient_key: str, now: datetime
    ) -> dict[str, Any] | None:
        from patient360.fga import parse_rfc3339

        rows = [
            self._row(aid, ev)
            for aid, ev in self.events
            if ev.event_type == "break_glass"
            and ev.agent_user == user_id
            and ev.entity_patient == patient_key
            and ev.outcome == "0"
            and parse_rfc3339(ev.detail["expiry"]) > now
        ]
        return rows[-1] if rows else None

    def of_type(self, event_type: str) -> list[AuditEvent]:
        return [ev for _, ev in self.events if ev.event_type == event_type]

    async def log_aggregate(
        self,
        *,
        session_id: str | None,
        user_id: str,
        dataset: str,
        group_by: list[str],
        filters: dict[str, Any],
        cells: list[dict[str, Any]],
        suppressed_cells: int,
        k_min: int | None,
        audit_id: UUID | None,
    ) -> None:
        self.aggregates.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "dataset": dataset,
                "group_by": group_by,
                "filters": filters,
                "cells": cells,
                "suppressed_cells": suppressed_cells,
                "k_min": k_min,
                "audit_id": audit_id,
            }
        )

    async def session_aggregates(self, session_id: str) -> list[dict[str, Any]]:
        return [a for a in self.aggregates if a["session_id"] == session_id]

    async def list_events(self, *, limit: int = 100, agent_user: str | None = None) -> list[dict[str, Any]]:
        rows = [self._row(aid, ev) for aid, ev in reversed(self.events)]
        if agent_user:
            rows = [r for r in rows if r.get("agent_user") == agent_user]
        return rows[:limit]


class FakeFga:
    policy_version = "fga:test-model"

    def __init__(self, tuples: Sequence[Tuple] | None = None) -> None:
        self.tuples: list[Tuple] = list(DEMO_TUPLES if tuples is None else tuples)
        self.calls: list[tuple[str, str, str, datetime]] = []
        self.writes: list[tuple[list[Tuple], list[Tuple]]] = []
        self.fail = False
        self.fail_writes = False

    def _raise_if_down(self) -> None:
        if self.fail:
            from patient360.fga import FgaUnavailable

            raise FgaUnavailable("down")

    def _live(self, user: str, relation: str, obj: str, now: datetime) -> bool:
        return any(
            t.user == user
            and t.relation == relation
            and t.object == obj
            and (t.window is None or t.window.is_live(now))
            for t in self.tuples
        )

    def _holds(self, user: str, permission: str, obj: str, now: datetime) -> bool:
        if self._live(user, "blocked", obj, now):
            return False
        rels = PERMISSION_RELATIONS.get(permission)
        if rels is None:
            return False
        if any(self._live(user, r, obj, now) for r in rels):
            return True
        if permission == "can_read_diet":  # staff from admitted_to
            for t in self.tuples:
                if (
                    t.relation == "admitted_to"
                    and t.object == obj
                    and (t.window is None or t.window.is_live(now))
                ):
                    if self._live(user, "staff", t.user, now):
                        return True
        return False

    async def check(self, user: str, relation: str, obj: str, now: datetime) -> bool:
        self._raise_if_down()
        self.calls.append((user, relation, obj, now))
        return self._holds(user, relation, obj, now)

    async def list_objects(self, user: str, relation: str, type_: str, now: datetime) -> list[str]:
        self._raise_if_down()
        objects = {t.object for t in self.tuples if t.object.startswith(type_ + ":")}
        return sorted(o for o in objects if self._holds(user, relation, o, now))

    async def write(self, writes: Sequence[Tuple] = (), deletes: Sequence[Tuple] = ()) -> None:
        self._raise_if_down()
        if self.fail_writes:
            from patient360.fga import FgaUnavailable

            raise FgaUnavailable("write down")
        existing = {t.key for t in self.tuples}
        for t in writes:
            if t.key in existing:
                raise TupleExists(str(t.key))
        for t in deletes:
            if t.key not in existing:
                raise TupleMissing(str(t.key))
        # Atomic: validated above, applied here.
        self.tuples = [t for t in self.tuples if t.key not in {d.key for d in deletes}]
        self.tuples.extend(writes)
        self.writes.append((list(writes), list(deletes)))

    async def read(self, obj: str, relation: str | None = None, user: str | None = None) -> list[Tuple]:
        self._raise_if_down()
        return [
            t
            for t in self.tuples
            if t.object == obj
            and (relation is None or t.relation == relation)
            and (user is None or t.user == user)
        ]

    def has(self, user: str, relation: str, obj: str) -> bool:
        return any(t.key == (user, relation, obj) for t in self.tuples)


class FakeUsers:
    def __init__(self, users: dict[str, User] | None = None) -> None:
        self.users = dict(USERS if users is None else users)

    async def get(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    async def list_care(self) -> list[User]:
        from patient360.auth.sessions import PRACTITIONER_ROLES

        return sorted(
            (u for u in self.users.values() if u.active and u.role in PRACTITIONER_ROLES),
            key=lambda u: u.user_id,
        )


class FakeSessions:
    def __init__(self) -> None:
        self.rows: dict[bytes, Session] = {}

    async def create(self, session: Session) -> None:
        self.rows[session.session_hash] = session

    async def get(self, session_hash: bytes) -> Session | None:
        s = self.rows.get(session_hash)
        return replace(s) if s else None  # copy, like a DB read

    async def touch(self, session_hash: bytes, *, last_seen_at: datetime, expires_at: datetime) -> None:
        s = self.rows[session_hash]
        s.last_seen_at = last_seen_at
        s.expires_at = expires_at

    async def revoke(self, session_hash: bytes, *, now: datetime) -> None:
        s = self.rows.get(session_hash)
        if s and s.revoked_at is None:
            s.revoked_at = now

    async def bind_sandbox(self, session_hash: bytes, sandbox_id: str) -> str:
        s = self.rows[session_hash]
        if s.sandbox_id is None and s.revoked_at is None:
            s.sandbox_id = sandbox_id
        if not s.sandbox_id:
            raise RuntimeError("sandbox bind failed")
        return s.sandbox_id


# clinical.patients birth years (seed_demo.py).
BIRTH_YEARS: dict[str, int] = {"p_101": 1961, "p_102": 1974, "p_103": 1958, "p_104": 2012, "p_205": 1989}
SEXES: dict[str, str] = {
    "p_101": "female",
    "p_102": "male",
    "p_103": "female",
    "p_104": "female",
    "p_205": "male",
}


class FakeClinical:
    def __init__(
        self,
        rows: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        birth_years: dict[str, int] | None = None,
        sexes: dict[str, str] | None = None,
    ) -> None:
        self.rows = rows or {}
        self.birth_years = dict(BIRTH_YEARS if birth_years is None else birth_years)
        self.sexes = dict(SEXES if sexes is None else sexes)
        self.calls: list[tuple[str, str]] = []
        self.aggregate_log: list[dict[str, Any]] = []
        self.appointment_rows: list[dict[str, Any]] = []
        self.note_rows: list[dict[str, Any]] = []
        self.study_rows: list[dict[str, Any]] = []
        self.report_rows: list[dict[str, Any]] = []

    async def patient_birth_year(self, patient_key: str) -> int | None:
        return self.birth_years.get(patient_key)

    async def fetch(
        self, dataset: str, patient_key: str, filters: QueryFilters, obligations: Obligations
    ) -> list[dict[str, Any]]:
        self.calls.append((dataset, patient_key))
        out = list(self.rows.get((dataset, patient_key), []))
        if obligations.allergy_category and dataset == "allergies":
            out = [r for r in out if obligations.allergy_category in (r.get("category") or [])]
        if filters.active_only and dataset == "meds":
            out = [r for r in out if r.get("status") == "active"]
        if filters.code:
            out = [r for r in out if r.get("code") == filters.code]
        if filters.category:
            out = [
                r
                for r in out
                if r.get("category") == filters.category or filters.category in (r.get("category") or [])
            ]
        if dataset == "encounters":
            out = out + list(self.rows.get(("appointments", patient_key), []))
        return out[: filters.limit]

    async def aggregate(
        self,
        dataset: str,
        group_by: list[str],
        filters: QueryFilters,
        obligations: Obligations,
        scoped_keys: tuple[str, ...] | None,
    ) -> list[dict[str, Any]]:
        from collections import Counter

        from patient360.tools.aggregate import age_display

        self.aggregate_log.append({"dataset": dataset, "group_by": group_by, "scoped_keys": scoped_keys})
        rows: list[dict[str, Any]] = []
        for (ds, key), items in self.rows.items():
            if ds != dataset:
                continue
            if scoped_keys is not None and key not in scoped_keys:
                continue
            for item in items:
                row = dict(item)
                row["_patient_key"] = key
                row["sex"] = self.sexes.get(key)
                row["birth_year"] = age_display(self.birth_years.get(key), 2026)
                rows.append(row)
        if obligations.allergy_category and dataset == "allergies":
            rows = [r for r in rows if obligations.allergy_category in (r.get("category") or [])]
        if filters.code:
            rows = [r for r in rows if r.get("code") == filters.code]
        if filters.category:
            rows = [
                r
                for r in rows
                if r.get("category") == filters.category or filters.category in (r.get("category") or [])
            ]
        if filters.active_only and dataset == "meds":
            rows = [r for r in rows if r.get("status") == "active"]
        counts: Counter[tuple[Any, ...]] = Counter()
        labels: dict[tuple[Any, ...], str] = {}
        for row in rows:
            key = tuple(row.get(d) for d in group_by)
            counts[key] += 1
            if key not in labels:
                label = row.get("display") or row.get("type_display")
                if label:
                    labels[key] = str(label)
        out: list[dict[str, Any]] = []
        for key, n in counts.items():
            cell = {d: key[i] for i, d in enumerate(group_by)}
            cell["count"] = n
            if key in labels:
                cell["display"] = labels[key]
            out.append(cell)
        return out

    async def get_appointment(self, appointment_id: UUID) -> dict[str, Any] | None:
        for row in self.appointment_rows:
            if row["id"] == appointment_id or str(row["id"]) == str(appointment_id):
                return dict(row)
        return None

    async def insert_appointment(self, row: dict[str, Any]) -> dict[str, Any]:
        stored = {
            "id": uuid4(),
            "cite_id": f"apt_{secrets_hex()}",
            **row,
        }
        self.appointment_rows.append(stored)
        key = row["patient_key"]
        self.rows.setdefault(("appointments", key), []).append(_appointment_as_encounter(stored))
        return dict(stored)

    async def update_appointment(self, appointment_id: UUID, fields: dict[str, Any]) -> dict[str, Any] | None:
        for row in self.appointment_rows:
            if row["id"] == appointment_id or str(row["id"]) == str(appointment_id):
                row.update(fields)
                key = row["patient_key"]
                self.rows[("appointments", key)] = [
                    _appointment_as_encounter(a)
                    for a in self.appointment_rows
                    if a["patient_key"] == key and a.get("status") in ("booked", "pending")
                ]
                return dict(row)
        return None

    async def list_notes(self, patient_key: str) -> list[dict[str, Any]]:
        extra = [
            dict(r) for r in self.note_rows if r.get("patient_key") == patient_key and r.get("published")
        ]
        return extra + list(self.rows.get(("notes", patient_key), []))

    async def list_imaging(self, patient_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        studies = [dict(r) for r in self.study_rows if r.get("patient_key") == patient_key]
        reports = [dict(r) for r in self.report_rows if r.get("patient_key") == patient_key]
        if not studies:
            studies = list(self.rows.get(("studies", patient_key), []))
        if not reports:
            reports = list(self.rows.get(("imaging", patient_key), []))
        return studies, reports

    async def get_study(self, patient_key: str, orthanc_id: str) -> dict[str, Any] | None:
        for row in self.study_rows:
            if row.get("patient_key") == patient_key and row.get("orthanc_id") == orthanc_id:
                return dict(row)
        for row in self.rows.get(("studies", patient_key), []):
            if row.get("orthanc_id") == orthanc_id:
                return dict(row)
        return None

    async def upsert_vista_report(self, row: dict[str, Any]) -> dict[str, Any]:
        stored = dict(row)
        stored.setdefault("id", uuid4())
        self.report_rows = [
            item for item in self.report_rows if item.get("source_id") != row.get("source_id")
        ]
        self.report_rows.append(stored)
        return stored

    async def booked_windows(
        self, *, practitioner_user_id: str | None, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        out = []
        for row in self.appointment_rows:
            if row.get("status") not in ("booked", "pending"):
                continue
            if practitioner_user_id and row["practitioner_user_id"] != practitioner_user_id:
                continue
            at = row["start_at"]
            if start <= at < end:
                out.append(
                    {
                        "practitioner_user_id": row["practitioner_user_id"],
                        "start_at": at,
                        "end_at": row.get("end_at"),
                    }
                )
        return out


def secrets_hex() -> str:
    return uuid4().hex[:8]


def _appointment_as_encounter(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cite_id": row.get("cite_id"),
        "status": row.get("status"),
        "class": "AMB",
        "type_display": row.get("service_type_display"),
        "started_at": row.get("start_at"),
        "ended_at": row.get("end_at"),
        "dept": row.get("dept"),
        "practitioner_user_id": row.get("practitioner_user_id"),
        "confidentiality": row.get("confidentiality", "N"),
        "sensitivity": row.get("sensitivity", []),
    }


def demo_rows() -> dict[tuple[str, str], list[dict[str, Any]]]:
    return {
        # p_104 (Lea, 14): what her guardian sees, and the adolescent-clinic rows labelled R + SEX.
        ("labs", "p_104"): [
            {
                "cite_id": "obs_d1",
                "code": "718-7",
                "display": "Hemoglobin",
                "value_num": 13.1,
                "unit": "g/dL",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "obs_d2",
                "code": "26449-9",
                "display": "Eosinophils",
                "value_num": 0.3,
                "unit": "10*3/uL",
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
        ("conditions", "p_104"): [
            {
                "cite_id": "cond_d1",
                "code": "195967001",
                "display": "Asthma",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "cond_d2",
                "code": "171057006",
                "display": "Pregnancy prevention education",
                "confidentiality": "R",
                "sensitivity": ["SEX"],
            },
        ],
        ("meds", "p_104"): [
            {
                "cite_id": "med_d1",
                "code": "745752",
                "display": "Albuterol inhaler",
                "status": "active",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "med_d2",
                "code": "748962",
                "display": "Levonorgestrel / ethinyl estradiol",
                "status": "active",
                "confidentiality": "R",
                "sensitivity": ["SEX"],
            },
        ],
        ("encounters", "p_104"): [
            {
                "cite_id": "enc_d1",
                "class": "AMB",
                "dept": "pediatrics",
                "reason_display": "Asthma",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "enc_d2",
                "class": "AMB",
                "dept": "adolescent-medicine",
                "reason_display": "Pregnancy prevention education",
                "confidentiality": "R",
                "sensitivity": ["SEX"],
            },
        ],
        ("labs", "p_101"): [
            {
                "cite_id": "obs_a1",
                "code": "4548-4",
                "display": "HbA1c",
                "value_num": 7.9,
                "unit": "%",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "obs_a2",
                "code": "2160-0",
                "display": "Creatinine",
                "value_num": 1.3,
                "unit": "mg/dL",
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
        ("conditions", "p_101"): [
            {
                "cite_id": "cond_a1",
                "code": "44054006",
                "display": "Type 2 diabetes",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "cond_a2",
                "code": "35489007",
                "display": "Depressive disorder",
                "confidentiality": "V",
                "sensitivity": ["PSY"],
            },
        ],
        ("meds", "p_101"): [
            {
                "cite_id": "med_a1",
                "code": "860975",
                "display": "Metformin",
                "status": "active",
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "med_a2",
                "code": "312940",
                "display": "Sertraline",
                "status": "active",
                "confidentiality": "R",
                "sensitivity": ["PSY"],
            },
            {
                "cite_id": "med_a3",
                "code": "310798",
                "display": "Lisinopril",
                "status": "stopped",
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
        ("allergies", "p_101"): [
            {
                "cite_id": "alg_a1",
                "display": "Peanut",
                "category": ["food"],
                "confidentiality": "N",
                "sensitivity": [],
            },
            {
                "cite_id": "alg_a2",
                "display": "Penicillin",
                "category": ["medication"],
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
        ("diet", "p_101"): [
            {
                "cite_id": "diet_a1",
                "diet_codes": ["160670007"],
                "ward": "w_3b",
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
        ("notes", "p_101"): [
            {
                "cite_id": "note_p101_admit",
                "note_id": "p101-admission-2026-09-10",
                "type_display": "Discharge summary",
                "authored_at": "2026-09-10T18:00:00+00:00",
                "internal": False,
                "published": True,
                "confidentiality": "N",
                "sensitivity": [],
                "patient_key": "p_101",
                "text": "<PERSON> admitted 10 September 2026 for glycemic control. Metformin continued.",
            },
            {
                "cite_id": "note_p101_psych",
                "note_id": "p101-psych-consult-2026-09-12",
                "type_display": "Consult note",
                "authored_at": "2026-09-12T15:30:00+00:00",
                "internal": True,
                "published": True,
                "confidentiality": "V",
                "sensitivity": ["PSY"],
                "patient_key": "p_101",
                "text": "Psychiatric consult: persistent low mood. Internal clinician note.",
            },
        ],
        ("notes", "p_103"): [
            {
                "cite_id": "note_p103_cardio",
                "note_id": "p103-cardiology-2026-05-20",
                "type_display": "History and physical note",
                "authored_at": "2026-05-20T11:40:00+00:00",
                "internal": False,
                "published": True,
                "confidentiality": "N",
                "sensitivity": [],
                "patient_key": "p_103",
                "text": "Cardiology history and physical: essential hypertension on amlodipine.",
            },
        ],
        ("studies", "p_101"): [
            {
                "cite_id": "study_p101_cxr",
                "patient_key": "p_101",
                "modality": "CR",
                "procedure_display": "Chest X-ray",
                "study_at": "2026-09-11T09:00:00+00:00",
                "orthanc_id": None,
                "confidentiality": "N",
            },
        ],
        ("imaging", "p_101"): [
            {
                "cite_id": "dr_p101_cxr",
                "patient_key": "p_101",
                "category": "RAD",
                "display": "Chest X-ray",
                "conclusion_text": "No acute cardiopulmonary process.",
                "report_ref": "reports/p_101/cxr.txt",
                "confidentiality": "N",
            },
        ],
        ("meds", "p_103"): [
            {
                "cite_id": "med_c1",
                "code": "197361",
                "display": "Amlodipine",
                "status": "active",
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
        ("labs", "p_205"): [
            {
                "cite_id": "obs_e1",
                "code": "2160-0",
                "display": "Creatinine",
                "value_num": 0.9,
                "unit": "mg/dL",
                "confidentiality": "N",
                "sensitivity": [],
            },
        ],
    }


def aggregate_cohort_rows() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """23 patients so k_min=5 has both visible and suppressed condition cells."""
    rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    # 12 diabetes, 6 asthma, 3 MI, 2 fever. Complementary keeps A+B (two unsuppressed).
    spec: list[tuple[str, str, int]] = [
        ("44054006", "Type 2 diabetes", 12),
        ("195967001", "Asthma", 6),
        ("22298006", "Myocardial infarction", 3),
        ("386661006", "Fever", 2),
    ]
    n = 0
    for code, display, count in spec:
        for _ in range(count):
            n += 1
            key = f"p_a{n:02d}"
            SEXES[key] = "female" if n % 2 else "male"
            BIRTH_YEARS[key] = 1960 + (n % 20)
            rows[("conditions", key)] = [
                {"cite_id": f"cond_a{n:02d}", "code": code, "display": display, "confidentiality": "N"}
            ]
            rows[("labs", key)] = [
                {"cite_id": f"obs_a{n:02d}", "code": "4548-4", "display": "HbA1c", "confidentiality": "N"}
            ]
    return rows


def demo_note_chunks() -> list[dict[str, Any]]:
    return [
        {
            "patient_key": "p_101",
            "note_id": "p101-admission-2026-09-10",
            "cite_id": "note_p101_admit",
            "confidentiality": "N",
            "sensitivity": [],
            "published": True,
            "internal": False,
            "provenance": "clinical",
            "text": "<PERSON> admitted 10 September 2026 for glycemic control. Metformin continued.",
        },
        {
            "patient_key": "p_101",
            "note_id": "p101-psych-consult-2026-09-12",
            "cite_id": "note_p101_psych",
            "confidentiality": "V",
            "sensitivity": ["PSY"],
            "published": True,
            "internal": True,
            "provenance": "clinical",
            "text": "Psychiatric consult: persistent low mood. Internal clinician note.",
        },
        {
            "patient_key": "p_103",
            "note_id": "p103-cardiology-2026-05-20",
            "cite_id": "note_p103_cardio",
            "confidentiality": "N",
            "sensitivity": [],
            "published": True,
            "internal": False,
            "provenance": "clinical",
            "text": "Cardiology history and physical: essential hypertension on amlodipine.",
        },
    ]


def complementary_leak_rows() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """12 + 3: after k-min the large cell is the only unsuppressed sibling and must blank."""
    rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for i in range(12):
        key = f"p_c{i:02d}"
        SEXES[key] = "female"
        BIRTH_YEARS[key] = 1970
        rows[("conditions", key)] = [{"cite_id": f"cond_c{i}", "code": "44054006", "confidentiality": "N"}]
    for i in range(3):
        key = f"p_r{i:02d}"
        SEXES[key] = "female"
        BIRTH_YEARS[key] = 1970
        rows[("conditions", key)] = [{"cite_id": f"cond_r{i}", "code": "386661006", "confidentiality": "N"}]
    return rows
