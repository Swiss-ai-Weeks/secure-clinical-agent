"""Dashboard media sign + fetch. Pixels never go through the agent."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent
from .auth.sessions import utcnow
from .auth.subject import DepsDep, SessionCallerDep
from .errors import Deny, NotFound, Unauthenticated
from .pdp import Context, Resource, evaluate
from .pdp.models import PURPOSE_BY_ROLE

router = APIRouter(prefix="/media", tags=["media"])
ALGORITHM = "HS256"
AUD = "patient360-media"


class SignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_key: str = Field(..., pattern=r"^p_[0-9a-z]+$", max_length=64)
    study_id: str | None = None
    object_key: str | None = None


def _sign(settings, *, sub: str, sid: str, study_uid: str, scope: str, now: datetime) -> tuple[str, str]:
    jti = secrets.token_hex(16)
    exp = now + timedelta(seconds=settings.media_ttl_seconds)
    token = jwt.encode(
        {
            "iss": settings.run_token_issuer,
            "aud": AUD,
            "sub": sub,
            "sid": sid,
            "study_uid": study_uid,
            "scope": scope,
            "exp": int(exp.timestamp()),
            "iat": int(now.timestamp()),
            "jti": jti,
        },
        settings.run_token_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )
    return token, jti


def _verify(settings, token: str, *, now: datetime) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.run_token_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=AUD,
            issuer=settings.run_token_issuer,
            leeway=0,
        )
    except jwt.PyJWTError as exc:
        raise Unauthenticated("invalid media token") from exc


@router.post("/sign")
async def media_sign(body: SignRequest, caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    now = utcnow()
    rtype = "document_bytes" if body.object_key else "imaging_pixels"
    resource = Resource(type=rtype, patient_key=body.patient_key)
    purpose = PURPOSE_BY_ROLE.get(caller.subject.role, "HOPERAT")
    decision = await evaluate(
        caller.subject,
        resource,
        Context(now=now, channel="dashboard", purpose=purpose, action="read"),
        deps.fga.check,
    )
    decision.audit_id = await deps.audit.write(
        AuditEvent(
            event_type="media_sign",
            agent_user=caller.user.user_id,
            purpose_of_event=purpose,
            entity_patient=body.patient_key,
            entity_resource=body.object_key or body.study_id or rtype,
            outcome=OUTCOME_SUCCESS if decision.permitted else OUTCOME_MINOR,
            outcome_desc=decision.effect,
            policy_id=decision.policy_id,
            policy_version=deps.policy_version,
            reason_code=decision.reason_code,
            session_id=caller.sid,
        )
    )
    if decision.effect == "not_found":
        raise NotFound()
    if decision.effect == "deny":
        raise Deny(decision.reason_code, decision.audit_id)
    target = body.object_key or body.study_id or "study"
    token, jti = _sign(
        deps.settings, sub=caller.user.user_id, sid=caller.sid, study_uid=target, scope=rtype, now=now
    )
    return {
        "url": f"/media/{token}/{target}",
        "expires_in": deps.settings.media_ttl_seconds,
        "jti": jti,
        "audit_id": str(decision.audit_id),
    }


@router.get("/{token}/{path:path}")
async def media_fetch(token: str, path: str, caller: SessionCallerDep, deps: DepsDep) -> dict[str, Any]:
    now = utcnow()
    claims = _verify(deps.settings, token, now=now)
    if claims.get("sid") != caller.sid or claims.get("sub") != caller.user.user_id:
        raise Unauthenticated("media token session mismatch")
    study_uid = str(claims.get("study_uid") or "")
    if path != study_uid and not path.startswith(study_uid):
        raise NotFound()
    # Patient-level QIDO search is stripped: the signed path is one study or object only.
    data = await deps.objects.get("reports", study_uid)
    await deps.audit.write(
        AuditEvent(
            event_type="media_fetch",
            agent_user=caller.user.user_id,
            purpose_of_event=PURPOSE_BY_ROLE.get(caller.subject.role, "HOPERAT"),
            entity_resource=study_uid,
            outcome=OUTCOME_SUCCESS if data is not None else OUTCOME_MINOR,
            outcome_desc="bytes" if data is not None else "missing",
            session_id=caller.sid,
            jti=str(claims.get("jti")),
        )
    )
    if data is None:
        raise NotFound()
    return {"study_uid": study_uid, "bytes_b64": data.decode("latin1"), "length": len(data)}
