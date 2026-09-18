"""Linkage vault (Build Plan §4.5): the only place real identity persists.

Two KV v2 paths under {mount}/linkage/:
  self/{user_id}          -> {"patient_key": "p_xxx"}      portal login -> own record
  identity/{patient_key}  -> Identity record               real identity <-> pseudonym

Four operations, each audited by its caller:
  register              written by the ingestion worker / seed (worker token)
  resolve_self          at login, for patient and caregiver roles; copied into the
                        session row for the session lifetime and nowhere else
  identity_banner       GET /patients/{key}/identity, PDP-checked on a live relationship
  break_glass_identity  the re-identification read inside POST /break-glass (purpose BTG)

The backend's token can read self/* and identity/* and nothing else (openbao-init
policies). The API never returns more than the banner projection; address, phone
and national id stay in the vault. Names never pass through the agent channel.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import httpx

from .errors import Transient

log = logging.getLogger(__name__)

BANNER_FIELDS = ("patient_key", "given_name", "family_name", "birth_date", "sex", "mrn")


@dataclass(frozen=True, slots=True)
class Identity:
    patient_key: str
    given_name: str
    family_name: str
    birth_date: str  # full YYYY-MM-DD; the clinical store holds the year only
    sex: str
    mrn: str | None = None
    address: dict[str, Any] | None = None
    phone: str | None = None
    national_id: str | None = None

    def banner(self) -> dict[str, Any]:
        """What identity_banner and break_glass_identity may return: name, DOB, sex, MRN."""
        return {k: getattr(self, k) for k in BANNER_FIELDS}

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, patient_key: str, data: dict[str, Any]) -> Identity:
        return cls(
            patient_key=patient_key,
            given_name=str(data.get("given_name", "")),
            family_name=str(data.get("family_name", "")),
            birth_date=str(data.get("birth_date", "")),
            sex=str(data.get("sex", "unknown")),
            mrn=data.get("mrn"),
            address=data.get("address"),
            phone=data.get("phone"),
            national_id=data.get("national_id"),
        )


class LinkageVault(Protocol):
    async def resolve_self(self, user_id: str) -> str | None: ...

    async def read_identity(self, patient_key: str) -> Identity | None: ...


class OpenBaoVault:
    def __init__(
        self,
        url: str,
        token: str,
        *,
        mount: str = "secret",
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.mount = mount.strip("/")
        self._client = client or httpx.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"X-Vault-Token": token},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _read(self, path: str) -> dict[str, Any] | None:
        try:
            resp = await self._client.get(f"/v1/{self.mount}/data/linkage/{path}")
        except httpx.HTTPError as exc:
            log.error("vault transport error: %s", exc.__class__.__name__)
            raise Transient("vault unreachable") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            log.error("vault returned %s for linkage/%s", resp.status_code, path.split("/")[0])
            raise Transient(f"vault {resp.status_code}")
        return (resp.json().get("data") or {}).get("data") or {}

    async def resolve_self(self, user_id: str) -> str | None:
        data = await self._read(f"self/{user_id}")
        if not data:
            return None
        key = data.get("patient_key")
        return str(key) if key else None

    async def read_identity(self, patient_key: str) -> Identity | None:
        data = await self._read(f"identity/{patient_key}")
        if not data:
            return None
        return Identity.from_record(patient_key, data)


class StaticVault:
    """In-memory mapping for tests and for the inproc fallback."""

    def __init__(
        self, mapping: dict[str, str] | None = None, identities: dict[str, Identity] | None = None
    ) -> None:
        self.mapping = dict(mapping or {})
        self.identities = dict(identities or {})

    async def resolve_self(self, user_id: str) -> str | None:
        return self.mapping.get(user_id)

    async def read_identity(self, patient_key: str) -> Identity | None:
        return self.identities.get(patient_key)
