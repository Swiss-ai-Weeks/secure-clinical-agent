"""Run tokens (Build Plan §4.3): RFC 9068 at+JWT with an RFC 8693 act claim.

The agent carries identity it cannot read or forge. /chat (later slice) mints
one per run and registers it in the OpenShell credential store; the agent only
ever sees a placeholder. Tool endpoints verify signature, typ, iss, aud, exp,
act, then require the sid session to be live, so ending a session revokes every
token minted from it. jti is recorded on audit rows for correlation.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from ..config import Settings
from ..errors import Unauthenticated

ALGORITHM = "HS256"
TYP = "at+JWT"
IAT_LEEWAY_SECONDS = 30


@dataclass(frozen=True, slots=True)
class RunTokenClaims:
    sub: str  # user:u_xxx
    user_id: str
    act_sub: str  # agent:sbx_xx
    sid: str  # hex of session_hash
    jti: str
    iat: datetime
    exp: datetime


def mint(
    settings: Settings, *, user_id: str, sid: str, agent_id: str, now: datetime | None = None
) -> tuple[str, RunTokenClaims]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    exp = now + timedelta(seconds=settings.run_token_ttl_seconds)
    jti = secrets.token_hex(16)
    payload: dict[str, Any] = {
        "iss": settings.run_token_issuer,
        "sub": f"user:{user_id}",
        "act": {"sub": agent_id},
        "aud": settings.run_token_audience,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "sid": sid,
    }
    token = jwt.encode(
        payload, settings.run_token_secret.get_secret_value(), algorithm=ALGORITHM, headers={"typ": TYP}
    )
    return token, RunTokenClaims(
        sub=payload["sub"], user_id=user_id, act_sub=agent_id, sid=sid, jti=jti, iat=now, exp=exp
    )


def verify(settings: Settings, token: str, *, now: datetime | None = None) -> RunTokenClaims:
    """Signature, typ, iss, aud, exp, required claims, act.sub, sid shape. Raises Unauthenticated."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise Unauthenticated("malformed token") from exc
    typ = str(header.get("typ", ""))
    if typ.lower() not in (TYP.lower(), "application/at+jwt"):
        raise Unauthenticated("wrong typ")
    try:
        payload = jwt.decode(
            token,
            settings.run_token_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=settings.run_token_audience,
            issuer=settings.run_token_issuer,
            # Time claims are checked below against `now`, so callers can inject a clock.
            options={
                "require": ["exp", "iat", "iss", "aud", "sub", "jti"],
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
    except jwt.PyJWTError as exc:
        raise Unauthenticated(exc.__class__.__name__) from exc
    ts = int(now.timestamp())
    try:
        exp, iat = int(payload["exp"]), int(payload["iat"])
    except (TypeError, ValueError) as exc:
        raise Unauthenticated("bad time claims") from exc
    if ts >= exp:
        raise Unauthenticated("expired")
    if iat > ts + IAT_LEEWAY_SECONDS:
        raise Unauthenticated("issued in the future")
    if exp - iat > settings.run_token_ttl_seconds:
        raise Unauthenticated("lifetime exceeds policy")

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.startswith("user:"):
        raise Unauthenticated("bad sub")
    act = payload.get("act")
    if not isinstance(act, dict) or not isinstance(act.get("sub"), str) or not act["sub"]:
        raise Unauthenticated("missing act")
    sid = payload.get("sid")
    if not isinstance(sid, str) or len(sid) != 64:
        raise Unauthenticated("bad sid")
    try:
        bytes.fromhex(sid)
    except ValueError as exc:
        raise Unauthenticated("bad sid") from exc
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise Unauthenticated("bad jti")

    return RunTokenClaims(
        sub=sub,
        user_id=sub.removeprefix("user:"),
        act_sub=act["sub"],
        sid=sid,
        jti=jti,
        iat=datetime.fromtimestamp(int(payload["iat"]), UTC),
        exp=datetime.fromtimestamp(int(payload["exp"]), UTC),
    )
