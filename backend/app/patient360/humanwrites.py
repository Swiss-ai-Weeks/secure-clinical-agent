"""Human writes (Build Plan §4.2 write interface): consent grant, consent revoke, break-glass.

All three run on the dashboard channel only, after a PDP decision, and pair the
OpenFGA tuple change with an audit row written in the same handler. There is no
transaction spanning both stores, so the ordering is the guarantee:

  grant       write tuple -> consent_granted row; if the row fails, delete the tuple, 503
  revoke      delete tuple -> consent_revoked row; if the row fails, retry once, then 503
              (access is already gone, which is the safe side)
  break-glass write emergency tuple -> break_glass row (purpose BTG); if the row fails,
              delete the tuple, 503; then break_glass_identity -> identity_resolve row

The consent record is the consent_granted audit row: its id is the consent id.
Reading grants back joins OpenFGA Read (what is enforced now) with those rows
(how it got that way); neither alone is the record.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent, encode_query
from .errors import Conflict, Deny, Invalid, NotFound, Throttled, Transient
from .fga import Tuple, TupleExists, TupleMissing, Window, parse_rfc3339, rfc3339
from .pdp import Context, Decision, Resource, WriteTarget, evaluate
from .pdp.models import PURPOSE_BY_ROLE
from .pdp.relations import LISTED_RELATIONS

if TYPE_CHECKING:
    from .auth.subject import Caller
    from .deps import AppDeps

log = logging.getLogger(__name__)

# Relations OpenFGA holds without a window (deny-overrides).
UNWINDOWED_RELATIONS = frozenset({"blocked"})


# --- Records ------------------------------------------------------------------


@dataclass(slots=True)
class ConsentRecord:
    consent_id: UUID | None
    patient_key: str
    grantee_user_id: str
    relation: str
    start: datetime | None
    expiry: datetime | None
    status: str  # active | pending | expired | revoked | removed | store_only
    granted_by: str | None = None
    recorded_at: datetime | None = None
    justification: str | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    enforced: bool = False  # tuple present in OpenFGA right now
    seeded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "consent_id": str(self.consent_id) if self.consent_id else None,
            "patient_key": self.patient_key,
            "grantee_user_id": self.grantee_user_id,
            "relation": self.relation,
            "start": self.start,
            "expiry": self.expiry,
            "status": self.status,
            "granted_by": self.granted_by,
            "recorded_at": self.recorded_at,
            "justification": self.justification,
            "revoked_at": self.revoked_at,
            "revoked_by": self.revoked_by,
            "enforced": self.enforced,
            "seeded": self.seeded,
        }


@dataclass(slots=True)
class ConsentGrantRequest:
    patient_key: str
    grantee_user_id: str
    relation: str
    expiry: datetime | None
    start: datetime | None = None
    justification: str | None = None


@dataclass(slots=True)
class BreakGlassResult:
    patient_key: str
    start: datetime
    expiry: datetime
    audit_id: UUID
    decision_audit_id: UUID
    identity: dict[str, Any] | None
    identity_audit_id: UUID | None
    compliance_flag: bool = True


# --- Helpers ------------------------------------------------------------------


def _purpose(role: str) -> str:
    return PURPOSE_BY_ROLE.get(role, "HOPERAT")


def _tuple_for(patient_key: str, grantee: str, relation: str, window: Window | None) -> Tuple:
    return Tuple(f"user:{grantee}", relation, f"patient:{patient_key}", window)


def _whole_seconds(now: datetime) -> datetime:
    """Windows travel to OpenFGA at second precision; keep the audit row and the response identical."""
    return now.replace(microsecond=0)


async def _decision_row(
    deps: AppDeps,
    caller: Caller,
    decision: Decision,
    *,
    purpose: str,
    patient_key: str,
    resource: str,
    query: Any,
    extra: dict[str, Any] | None = None,
) -> UUID:
    return await deps.audit.write(
        AuditEvent(
            event_type="decision",
            agent_user=caller.user.user_id,
            purpose_of_event=purpose,
            entity_patient=patient_key,
            entity_resource=resource,
            entity_query=encode_query(query),
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            outcome_desc=decision.effect,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            reason_code=decision.reason_code,
            session_id=caller.sid,
            jti=caller.jti,
            detail={
                "channel": caller.channel,
                "relation": decision.relation,
                "fga_consulted": decision.fga_consulted,
                **(extra or {}),
            },
        )
    )


def _raise_for(decision: Decision) -> None:
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)


# --- Consents -----------------------------------------------------------------


async def grant_consent(
    deps: AppDeps, caller: Caller, req: ConsentGrantRequest, *, now: datetime
) -> ConsentRecord:
    now = _whole_seconds(now)
    subject = caller.subject
    purpose = _purpose(subject.role)
    grantee = await deps.users.get(req.grantee_user_id)
    grantee_role = grantee.role if grantee is not None and grantee.active else None
    target = WriteTarget(
        relation=req.relation, grantee_user_id=req.grantee_user_id, grantee_role=grantee_role
    )
    resource = Resource(type="consents", patient_key=req.patient_key)
    context = Context(now=now, channel=caller.channel, purpose=purpose, action="consent_grant", target=target)
    decision = await evaluate(subject, resource, context, deps.fga.check)
    query = {
        "patient_key": req.patient_key,
        "grantee_user_id": req.grantee_user_id,
        "relation": req.relation,
        "start": req.start,
        "expiry": req.expiry,
    }
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=req.patient_key,
        resource=f"consent/{req.relation}/{req.grantee_user_id}",
        query=query,
        extra={"action": "consent_grant"},
    )
    _raise_for(decision)

    # Window rules. `blocked` carries no window in the model; everything else must.
    window: Window | None = None
    if req.relation not in UNWINDOWED_RELATIONS:
        start = _whole_seconds(req.start) if req.start else now
        if req.expiry is None:
            raise Invalid("expiry_required", "A windowed grant needs an expiry")
        expiry = _whole_seconds(req.expiry)
        if expiry <= start:
            raise Invalid("expiry_before_start", "expiry must be after start")
        if expiry - start > timedelta(days=deps.settings.consent_max_days):
            raise Invalid("window_too_long", f"windows are limited to {deps.settings.consent_max_days} days")
        window = Window(start, expiry)

    tup = _tuple_for(req.patient_key, req.grantee_user_id, req.relation, window)
    try:
        await deps.fga.write(writes=[tup])
    except TupleExists:
        # Same key already present. A live window is a real conflict; an expired or
        # future one is renewed by replacing the tuple (two calls: the key cannot appear
        # in writes and deletes of one request).
        existing = [t for t in await deps.fga.read(tup.object, tup.relation, tup.user)]
        if (
            not existing
            or window is None
            or (existing[0].window is not None and existing[0].window.is_live(now))
        ):
            raise Conflict("consent_exists", decision.audit_id) from None
        await deps.fga.write(deletes=[existing[0]])
        await deps.fga.write(writes=[tup])

    detail = {
        "relation": req.relation,
        "grantee": req.grantee_user_id,
        "granted_by": subject.user_id,
        "basis": decision.reason_code,
        "start": rfc3339(window.start) if window else None,
        "expiry": rfc3339(window.expiry) if window else None,
        "justification": req.justification,
        "tuple": tup.as_dict(),
        "decision_audit_id": str(decision.audit_id),
        "seeded": False,
    }
    try:
        consent_id = await deps.audit.write(
            AuditEvent(
                event_type="consent_granted",
                agent_user=subject.user_id,
                purpose_of_event=purpose,
                entity_patient=req.patient_key,
                entity_resource=f"consent/{req.relation}/{req.grantee_user_id}",
                policy_id=decision.policy_id,
                policy_version=deps.policy_version,
                session_id=caller.sid,
                detail=detail,
            )
        )
    except Transient:
        # Access must never persist without a record.
        try:
            await deps.fga.write(deletes=[tup])
        except Exception as exc:  # pragma: no cover - logged, still fail closed
            log.error("consent rollback failed after audit failure: %s", exc.__class__.__name__)
        raise

    return ConsentRecord(
        consent_id=consent_id,
        patient_key=req.patient_key,
        grantee_user_id=req.grantee_user_id,
        relation=req.relation,
        start=window.start if window else None,
        expiry=window.expiry if window else None,
        status=_status(window, now, enforced=True),
        granted_by=subject.user_id,
        recorded_at=now,
        justification=req.justification,
        enforced=True,
    )


async def revoke_consent(deps: AppDeps, caller: Caller, consent_id: UUID, *, now: datetime) -> dict[str, Any]:
    subject = caller.subject
    purpose = _purpose(subject.role)
    row = await deps.audit_reader.get_consent(consent_id)
    if row is None:
        raise NotFound()
    detail = row.get("detail") or {}
    patient_key = row["entity_patient"]
    relation = detail.get("relation")
    grantee = detail.get("grantee")
    if not relation or not grantee or not patient_key:
        raise NotFound()

    target = WriteTarget(relation=relation, grantee_user_id=grantee, granted_by=row.get("agent_user"))
    resource = Resource(type="consents", patient_key=patient_key)
    context = Context(
        now=now, channel=caller.channel, purpose=purpose, action="consent_revoke", target=target
    )
    decision = await evaluate(subject, resource, context, deps.fga.check)
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=patient_key,
        resource=f"consent/{relation}/{grantee}",
        query={"consent_id": str(consent_id)},
        extra={"action": "consent_revoke"},
    )
    _raise_for(decision)

    events = await deps.audit_reader.consent_events(patient_key)
    if any(
        e["event_type"] == "consent_revoked" and (e.get("detail") or {}).get("consent_id") == str(consent_id)
        for e in events
    ):
        raise Conflict("already_revoked", decision.audit_id)

    tup = _tuple_for(patient_key, grantee, relation, None)
    removed = True
    try:
        await deps.fga.write(deletes=[tup])
    except TupleMissing:
        removed = False  # already gone (expired tuples still exist, so this means an operator removed it)

    event = AuditEvent(
        event_type="consent_revoked",
        agent_user=subject.user_id,
        purpose_of_event=purpose,
        entity_patient=patient_key,
        entity_resource=f"consent/{relation}/{grantee}",
        policy_id=decision.policy_id,
        policy_version=deps.policy_version,
        session_id=caller.sid,
        detail={
            "consent_id": str(consent_id),
            "relation": relation,
            "grantee": grantee,
            "revoked_by": subject.user_id,
            "tuple": tup.as_dict(),
            "tuple_removed": removed,
            "decision_audit_id": str(decision.audit_id),
        },
    )
    try:
        audit_id = await deps.audit.write(event)
    except Transient:
        log.warning("consent_revoked audit failed once; retrying (access already removed)")
        audit_id = await deps.audit.write(event)  # a second failure propagates as 503

    return {
        "consent_id": str(consent_id),
        "patient_key": patient_key,
        "grantee_user_id": grantee,
        "relation": relation,
        "revoked_at": now,
        "tuple_removed": removed,
        "audit_id": str(audit_id),
    }


def _status(window: Window | None, now: datetime, *, enforced: bool) -> str:
    if not enforced:
        return "removed"
    if window is None:
        return "active"
    if now < window.start:
        return "pending"
    if now >= window.expiry:
        return "expired"
    return "active"


async def list_consents(
    deps: AppDeps, caller: Caller, patient_key: str, *, now: datetime
) -> tuple[list[ConsentRecord], UUID]:
    subject = caller.subject
    purpose = _purpose(subject.role)
    resource = Resource(type="consents", patient_key=patient_key)
    context = Context(now=now, channel=caller.channel, purpose=purpose, action="read")
    decision = await evaluate(subject, resource, context, deps.fga.check)
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=patient_key,
        resource="consents",
        query={"patient_key": patient_key},
        extra={"action": "consents_list"},
    )
    _raise_for(decision)
    assert decision.audit_id is not None

    tuples = [t for t in await deps.fga.read(f"patient:{patient_key}") if t.relation in LISTED_RELATIONS]
    by_key = {t.key: t for t in tuples}
    events = await deps.audit_reader.consent_events(patient_key)

    revoked: dict[str, dict[str, Any]] = {}
    for e in events:
        if e["event_type"] == "consent_revoked":
            cid = (e.get("detail") or {}).get("consent_id")
            if cid:
                revoked[cid] = e

    records: list[ConsentRecord] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for e in events:
        if e["event_type"] != "consent_granted":
            continue
        d = e.get("detail") or {}
        relation, grantee = d.get("relation"), d.get("grantee")
        if not relation or not grantee:
            continue
        key = (f"user:{grantee}", relation, f"patient:{patient_key}")
        tup = by_key.get(key)
        start = parse_rfc3339(d["start"]) if d.get("start") else None
        expiry = parse_rfc3339(d["expiry"]) if d.get("expiry") else None
        window = tup.window if tup is not None else (Window(start, expiry) if start and expiry else None)
        rev = revoked.get(str(e["id"]))
        if rev is not None:
            status = "revoked"
        else:
            status = _status(window, now, enforced=tup is not None)
        if tup is not None and rev is None:
            seen_keys.add(key)
        records.append(
            ConsentRecord(
                consent_id=e["id"],
                patient_key=patient_key,
                grantee_user_id=grantee,
                relation=relation,
                start=window.start if window else None,
                expiry=window.expiry if window else None,
                status=status,
                granted_by=e.get("agent_user") or d.get("granted_by"),
                recorded_at=e.get("recorded_at"),
                justification=d.get("justification"),
                revoked_at=rev.get("recorded_at") if rev else None,
                revoked_by=(rev.get("detail") or {}).get("revoked_by") if rev else None,
                enforced=tup is not None and rev is None,
                seeded=bool(d.get("seeded")),
            )
        )

    # Tuples with no live consent record: loaded by openfga-init or an operator, or re-imported
    # after a revoke. Shown as store_only next to the history so enforcement is never hidden.
    for t in tuples:
        if t.key in seen_keys:
            continue
        if any(
            r.grantee_user_id == t.user.removeprefix("user:")
            and r.relation == t.relation
            and r.status != "revoked"
            for r in records
        ):
            continue
        records.append(
            ConsentRecord(
                consent_id=None,
                patient_key=patient_key,
                grantee_user_id=t.user.removeprefix("user:"),
                relation=t.relation,
                start=t.window.start if t.window else None,
                expiry=t.window.expiry if t.window else None,
                status="store_only",
                enforced=True,
            )
        )

    return records, decision.audit_id


# --- Break-glass ---------------------------------------------------------------


@dataclass
class BreakGlassLimiter:
    """Per-user activation limit, in memory (one process). A lab guard, not the policy."""

    per_hour: int
    _events: dict[str, deque[datetime]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, user_id: str, now: datetime) -> None:
        q = self._events[user_id]
        while q and now - q[0] > timedelta(hours=1):
            q.popleft()
        if len(q) >= self.per_hour:
            retry = int((q[0] + timedelta(hours=1) - now).total_seconds()) + 1
            raise Throttled(max(retry, 1))

    def record(self, user_id: str, now: datetime) -> None:
        self._events[user_id].append(now)


async def break_glass(
    deps: AppDeps, caller: Caller, patient_key: str, justification: str, *, now: datetime
) -> BreakGlassResult:
    now = _whole_seconds(now)
    subject = caller.subject
    purpose = "BTG"
    resource = Resource(type="clinical_rows", patient_key=patient_key)
    context = Context(now=now, channel=caller.channel, purpose=purpose, action="break_glass")
    decision = await evaluate(subject, resource, context, deps.fga.check)
    decision.audit_id = await _decision_row(
        deps,
        caller,
        decision,
        purpose=purpose,
        patient_key=patient_key,
        resource="break_glass",
        query={"patient_key": patient_key},
        extra={"action": "break_glass"},
    )
    _raise_for(decision)
    assert decision.audit_id is not None

    deps.break_glass_limiter.check(subject.user_id, now)

    expiry = now + timedelta(minutes=deps.settings.break_glass_minutes)
    tup = _tuple_for(patient_key, subject.user_id, "emergency", Window(now, expiry))
    try:
        await deps.fga.write(writes=[tup])
    except TupleExists:
        # An earlier activation is still on the store (live or expired): replace its window.
        existing = await deps.fga.read(tup.object, tup.relation, tup.user)
        if existing:
            await deps.fga.write(deletes=[existing[0]])
        await deps.fga.write(writes=[tup])

    try:
        audit_id = await deps.audit.write(
            AuditEvent(
                event_type="break_glass",
                agent_user=subject.user_id,
                purpose_of_event=purpose,
                entity_patient=patient_key,
                entity_resource="tuple/emergency",
                policy_id=decision.policy_id,
                policy_version=deps.policy_version,
                session_id=caller.sid,
                detail={
                    "justification": justification,
                    "start": rfc3339(now),
                    "expiry": rfc3339(expiry),
                    "compliance_flag": True,
                    "tuple": tup.as_dict(),
                    "decision_audit_id": str(decision.audit_id),
                    "auth_level": subject.auth_level,
                },
            )
        )
    except Transient:
        try:
            await deps.fga.write(deletes=[tup])
        except Exception as exc:  # pragma: no cover
            log.error("break-glass rollback failed after audit failure: %s", exc.__class__.__name__)
        raise
    deps.break_glass_limiter.record(subject.user_id, now)

    # break_glass_identity: the sanctioned re-identification read, audited with purpose BTG.
    identity_out: dict[str, Any] | None = None
    identity_audit_id: UUID | None = None
    identity = await deps.vault.read_identity(patient_key)
    identity_audit_id = await deps.audit.write(
        AuditEvent(
            event_type="identity_resolve",
            agent_user=subject.user_id,
            purpose_of_event=purpose,
            entity_patient=patient_key,
            entity_resource="vault/identity",
            outcome=OUTCOME_SUCCESS if identity is not None else OUTCOME_MINOR,
            outcome_desc="vault.break_glass_identity",
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            session_id=caller.sid,
            detail={
                "operation": "break_glass_identity",
                "resolved": identity is not None,
                "break_glass_audit_id": str(audit_id),
            },
        )
    )
    if identity is not None:
        identity_out = identity.banner()

    return BreakGlassResult(
        patient_key=patient_key,
        start=now,
        expiry=expiry,
        audit_id=audit_id,
        decision_audit_id=decision.audit_id,
        identity=identity_out,
        identity_audit_id=identity_audit_id,
    )


async def active_break_glass(
    deps: AppDeps, user_id: str, patient_key: str, now: datetime
) -> dict[str, Any] | None:
    """Live break-glass activation by this user on this patient, read from the audit log."""
    return await deps.audit_reader.active_break_glass(user_id, patient_key, now)
