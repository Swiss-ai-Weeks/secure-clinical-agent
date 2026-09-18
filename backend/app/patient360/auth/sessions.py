"""Server-side sessions (Build Plan §4.4; identity.sessions in 03-identity.sql).

The cookie carries a CSPRNG 128-bit token; the row is keyed by sha256(token),
so a read of the table yields no usable cookie. auth_level is the NIST AAL of
the login event. Inactivity expiry slides on each authenticated request up to
the absolute expiry. self_patient_id is filled by one vault call at login and
disappears with the row.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from ..audit import AuditEvent, AuditWriter
from ..config import Settings
from ..db import Database
from ..devlogin import DevLoginMap
from ..errors import Transient, Unauthenticated
from ..vault import LinkageVault

log = logging.getLogger(__name__)

SELF_ROLES = frozenset({"patient", "caregiver"})


@dataclass(frozen=True, slots=True)
class User:
    user_id: str
    role: str
    department: str | None
    credential_level: int
    active: bool


@dataclass(slots=True)
class Session:
    session_hash: bytes
    user_id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    absolute_expires_at: datetime
    auth_level: int
    on_duty: bool
    self_patient_id: str | None
    sandbox_id: str | None
    revoked_at: datetime | None

    @property
    def sid(self) -> str:
        """Hex of session_hash: the value on run tokens and audit rows."""
        return self.session_hash.hex()

    def is_live(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at and now < self.absolute_expires_at


def new_token() -> str:
    return secrets.token_hex(16)  # 128 bits


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def utcnow() -> datetime:
    return datetime.now(UTC)


PRACTITIONER_ROLES = frozenset({"attending", "care_team", "consultant"})


class UserRepo(Protocol):
    async def get(self, user_id: str) -> User | None: ...

    async def list_care(self) -> list[User]:
        """Active attending / care_team / consultant rows (availability, booking)."""
        ...


class SessionStore(Protocol):
    async def create(self, session: Session) -> None: ...

    async def get(self, session_hash: bytes) -> Session | None: ...

    async def touch(self, session_hash: bytes, *, last_seen_at: datetime, expires_at: datetime) -> None: ...

    async def revoke(self, session_hash: bytes, *, now: datetime) -> None: ...


# --- Postgres implementations -------------------------------------------------


class PgUserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, user_id: str) -> User | None:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT user_id, role, department, credential_level, active "
                    "FROM identity.users WHERE user_id = %s",
                    (user_id,),
                )
                row = await cur.fetchone()
        except Exception as exc:
            log.error("user read failed: %s", exc.__class__.__name__)
            raise Transient("identity unavailable") from exc
        return User(**row) if row else None

    async def list_care(self) -> list[User]:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT user_id, role, department, credential_level, active "
                    "FROM identity.users WHERE active AND role = ANY(%s) ORDER BY user_id",
                    (list(PRACTITIONER_ROLES),),
                )
                rows = await cur.fetchall()
        except Exception as exc:
            log.error("user list failed: %s", exc.__class__.__name__)
            raise Transient("identity unavailable") from exc
        return [User(**row) for row in rows]


_SESSION_COLS = (
    "session_hash, user_id, created_at, last_seen_at, expires_at, absolute_expires_at, "
    "auth_level, on_duty, self_patient_id, sandbox_id, revoked_at"
)


class PgSessionStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, s: Session) -> None:
        try:
            async with self.db.pool.connection() as conn:
                await conn.execute(
                    f"INSERT INTO identity.sessions ({_SESSION_COLS}) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        s.session_hash,
                        s.user_id,
                        s.created_at,
                        s.last_seen_at,
                        s.expires_at,
                        s.absolute_expires_at,
                        s.auth_level,
                        s.on_duty,
                        s.self_patient_id,
                        s.sandbox_id,
                        s.revoked_at,
                    ),
                )
        except Exception as exc:
            log.error("session insert failed: %s", exc.__class__.__name__)
            raise Transient("identity unavailable") from exc

    async def get(self, session_hash: bytes) -> Session | None:
        try:
            async with self.db.pool.connection() as conn:
                cur = await conn.execute(
                    f"SELECT {_SESSION_COLS} FROM identity.sessions WHERE session_hash = %s", (session_hash,)
                )
                row = await cur.fetchone()
        except Exception as exc:
            log.error("session read failed: %s", exc.__class__.__name__)
            raise Transient("identity unavailable") from exc
        return Session(**_normalise(row)) if row else None

    async def touch(self, session_hash: bytes, *, last_seen_at: datetime, expires_at: datetime) -> None:
        try:
            async with self.db.pool.connection() as conn:
                await conn.execute(
                    "UPDATE identity.sessions SET last_seen_at = %s, expires_at = %s WHERE session_hash = %s",
                    (last_seen_at, expires_at, session_hash),
                )
        except Exception as exc:
            log.error("session touch failed: %s", exc.__class__.__name__)
            raise Transient("identity unavailable") from exc

    async def revoke(self, session_hash: bytes, *, now: datetime) -> None:
        try:
            async with self.db.pool.connection() as conn:
                await conn.execute(
                    "UPDATE identity.sessions SET revoked_at = %s "
                    "WHERE session_hash = %s AND revoked_at IS NULL",
                    (now, session_hash),
                )
        except Exception as exc:
            log.error("session revoke failed: %s", exc.__class__.__name__)
            raise Transient("identity unavailable") from exc


def _normalise(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    sh = out["session_hash"]
    out["session_hash"] = bytes(sh) if not isinstance(sh, bytes) else sh
    return out


# --- Service ------------------------------------------------------------------


@dataclass(slots=True)
class LoginResult:
    token: str
    session: Session
    user: User


class SessionManager:
    """Login, authenticate (with sliding expiry), logout. Writes login/logout/identity_resolve audit rows."""

    def __init__(
        self,
        *,
        settings: Settings,
        users: UserRepo,
        sessions: SessionStore,
        vault: LinkageVault,
        audit: AuditWriter,
        devlogin: DevLoginMap,
    ) -> None:
        self.settings = settings
        self.users = users
        self.sessions = sessions
        self.vault = vault
        self.audit = audit
        self.devlogin = devlogin

    def _lifetimes(self, now: datetime) -> tuple[datetime, datetime]:
        absolute = now + timedelta(seconds=self.settings.session_absolute_seconds)
        inactivity = now + timedelta(seconds=self.settings.session_inactivity_seconds)
        return min(inactivity, absolute), absolute

    async def login(
        self,
        login: str,
        *,
        on_duty: bool = True,
        auth_level: int = 1,
        prior_cookie: str | None = None,
        now: datetime | None = None,
    ) -> LoginResult:
        now = now or utcnow()
        persona = self.devlogin.resolve(login)
        if persona is None:
            raise Unauthenticated("unknown login")
        user = await self.users.get(persona.user_id)
        if user is None or not user.active:
            raise Unauthenticated("inactive or unknown user")

        # Rotate: a cookie presented at login is revoked before the new row exists.
        if prior_cookie:
            await self.sessions.revoke(hash_token(prior_cookie), now=now)

        self_patient_id: str | None = None
        if user.role in SELF_ROLES:
            self_patient_id = await self.vault.resolve_self(user.user_id)

        token = new_token()
        expires_at, absolute_expires_at = self._lifetimes(now)
        session = Session(
            session_hash=hash_token(token),
            user_id=user.user_id,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
            auth_level=auth_level,
            on_duty=on_duty,
            self_patient_id=self_patient_id,
            sandbox_id=None,
            revoked_at=None,
        )
        await self.sessions.create(session)

        if user.role in SELF_ROLES:
            await self.audit.write(
                AuditEvent(
                    event_type="identity_resolve",
                    agent_user=user.user_id,
                    purpose_of_event="PATRQT",
                    entity_patient=self_patient_id,
                    session_id=session.sid,
                    outcome_desc="vault.resolve_self",
                    detail={"resolved": self_patient_id is not None},
                )
            )
        await self.audit.write(
            AuditEvent(
                event_type="login",
                agent_user=user.user_id,
                session_id=session.sid,
                detail={
                    "auth_level": auth_level,
                    "on_duty": on_duty,
                    "role": user.role,
                    "rotated": bool(prior_cookie),
                },
            )
        )
        return LoginResult(token=token, session=session, user=user)

    async def authenticate(self, cookie: str, *, now: datetime | None = None) -> tuple[Session, User]:
        """Cookie -> live session + active user, sliding the inactivity expiry."""
        now = now or utcnow()
        session = await self.sessions.get(hash_token(cookie))
        if session is None or not session.is_live(now):
            raise Unauthenticated("no live session")
        user = await self.users.get(session.user_id)
        if user is None or not user.active:
            raise Unauthenticated("inactive user")
        expires_at, _ = self._lifetimes(now)
        expires_at = min(expires_at, session.absolute_expires_at)
        await self.sessions.touch(session.session_hash, last_seen_at=now, expires_at=expires_at)
        session.last_seen_at = now
        session.expires_at = expires_at
        return session, user

    async def session_for_sid(self, sid: str, *, now: datetime | None = None) -> tuple[Session, User]:
        """Run-token path: sid (hex of session_hash) -> live session + active user. Does not slide expiry."""
        now = now or utcnow()
        try:
            session_hash = bytes.fromhex(sid)
        except ValueError as exc:
            raise Unauthenticated("bad sid") from exc
        if len(session_hash) != 32:
            raise Unauthenticated("bad sid")
        session = await self.sessions.get(session_hash)
        if session is None or not session.is_live(now):
            raise Unauthenticated("session not live")
        user = await self.users.get(session.user_id)
        if user is None or not user.active:
            raise Unauthenticated("inactive user")
        return session, user

    async def logout(self, cookie: str, *, now: datetime | None = None) -> None:
        now = now or utcnow()
        session_hash = hash_token(cookie)
        session = await self.sessions.get(session_hash)
        await self.sessions.revoke(session_hash, now=now)
        if session is not None:
            await self.audit.write(
                AuditEvent(event_type="logout", agent_user=session.user_id, session_id=session.sid)
            )
