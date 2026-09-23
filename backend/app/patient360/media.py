"""Dashboard media sign + fetch. Pixels never go through the agent."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .audit import OUTCOME_MINOR, OUTCOME_SUCCESS, AuditEvent
from .auth.sessions import utcnow
from .auth.subject import DepsDep, SessionCallerDep
from .dicom import DicomWebResult, parse_dicomweb_path, sanitize_dicomweb_query
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


def _sign(
    settings,
    *,
    sub: str,
    sid: str,
    study_uid: str,
    scope: str,
    now: datetime,
    study_instance_uid: str | None = None,
) -> tuple[str, str]:
    jti = secrets.token_hex(16)
    exp = now + timedelta(seconds=settings.media_ttl_seconds)
    payload = {
        "iss": settings.run_token_issuer,
        "aud": AUD,
        "sub": sub,
        "sid": sid,
        "study_uid": study_uid,
        "scope": scope,
        "exp": int(exp.timestamp()),
        "iat": int(now.timestamp()),
        "jti": jti,
    }
    if study_instance_uid:
        payload["study_instance_uid"] = study_instance_uid
    token = jwt.encode(
        payload,
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
    study_instance_uid = None
    if rtype == "imaging_pixels" and deps.dicom is not None:
        study_instance_uid = await deps.dicom.study_instance_uid(target)
    token, jti = _sign(
        deps.settings,
        sub=caller.user.user_id,
        sid=caller.sid,
        study_uid=target,
        scope=rtype,
        now=now,
        study_instance_uid=study_instance_uid,
    )
    out: dict[str, Any] = {
        "url": f"/media/{token}/{target}",
        "expires_in": deps.settings.media_ttl_seconds,
        "jti": jti,
        "audit_id": str(decision.audit_id),
    }
    if study_instance_uid:
        out["study_instance_uid"] = study_instance_uid
    return out


@router.get("/{token}/{path:path}")
async def media_fetch(
    token: str, path: str, request: Request, caller: SessionCallerDep, deps: DepsDep
) -> Any:
    now = utcnow()
    claims = _verify(deps.settings, token, now=now)
    if claims.get("sid") != caller.sid or claims.get("sub") != caller.user.user_id:
        raise Unauthenticated("media token session mismatch")
    study_uid = str(claims.get("study_uid") or "")
    if path == "dicom-web" or path.startswith("dicom-web/"):
        return await _dicomweb_proxy(path, request, caller, deps, claims)
    if path != study_uid and not path.startswith(study_uid):
        raise NotFound()
    # Patient-level QIDO search is stripped: the signed path is one study or object only.
    data = None
    if claims.get("scope") == "imaging_pixels" and deps.dicom is not None:
        data = await deps.dicom.preview(study_uid)
    if data is None:
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


async def _dicomweb_proxy(
    path: str, request: Request, caller: SessionCallerDep, deps: DepsDep, claims: dict[str, Any]
) -> StreamingResponse:
    if claims.get("scope") != "imaging_pixels" or deps.dicom is None:
        raise NotFound()
    study_instance_uid = str(claims.get("study_instance_uid") or "")
    if not study_instance_uid:
        orthanc_id = str(claims.get("study_uid") or "")
        study_instance_uid = str(await deps.dicom.study_instance_uid(orthanc_id) or "")
    if not study_instance_uid:
        raise NotFound()
    rel = path[len("dicom-web") :].lstrip("/")
    parsed = parse_dicomweb_path(rel)
    if parsed is None:
        raise NotFound()
    if parsed.study_uid and parsed.study_uid != study_instance_uid:
        raise NotFound()
    query = sanitize_dicomweb_query(
        {key: request.query_params[key] for key in request.query_params.keys()},
        study_uid=study_instance_uid,
        kind=parsed.kind,
    )
    if query is None:
        raise NotFound()
    result = await deps.dicom.dicomweb(parsed.upstream, query)
    if result is None:
        await _audit_dicomweb(caller, deps, claims, parsed, study_instance_uid, found=False)
        raise NotFound()
    await _audit_dicomweb(caller, deps, claims, parsed, study_instance_uid, found=True)
    return StreamingResponse(
        _iter_body(result),
        status_code=result.status_code,
        media_type=result.content_type,
        headers={"Cache-Control": "no-store"},
    )


async def _audit_dicomweb(
    caller: SessionCallerDep,
    deps: DepsDep,
    claims: dict[str, Any],
    parsed,
    study_instance_uid: str,
    *,
    found: bool,
) -> None:
    if parsed.kind == "frame":
        return
    await deps.audit.write(
        AuditEvent(
            event_type="media_fetch",
            agent_user=caller.user.user_id,
            purpose_of_event=PURPOSE_BY_ROLE.get(caller.subject.role, "HOPERAT"),
            entity_resource=parsed.series_uid or study_instance_uid,
            outcome=OUTCOME_SUCCESS if found else OUTCOME_MINOR,
            outcome_desc="dicom-web" if found else "missing",
            session_id=caller.sid,
            jti=str(claims.get("jti")),
        )
    )


async def _iter_body(result: DicomWebResult) -> AsyncIterator[bytes]:
    if isinstance(result.body, (bytes, bytearray)):
        yield bytes(result.body)
        return
    async for chunk in result.body:
        yield chunk
