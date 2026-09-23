from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from patient360.config import Settings
from patient360.deps import AppDeps
from patient360.devlogin import DevLoginMap
from patient360.main import create_app
from patient360.tools.stores import MemoryNotes, MemoryObjects
from patient360.vault import StaticVault

from .fakes import (
    IDENTITIES,
    VAULT,
    FakeAudit,
    FakeClinical,
    FakeFga,
    FakeSessions,
    FakeUsers,
    demo_note_chunks,
    demo_rows,
)

DEVLOGIN = Path(__file__).resolve().parents[1] / "patient360" / "devlogin.demo.json"


def make_settings(**overrides) -> Settings:
    base = dict(
        db_dsn="postgres://unused",
        openfga_key="test-key",
        linkage_token="test-token",
        run_token_secret="test-run-token-secret-0123456789abcdef",
        dev=True,
        cookie_secure=False,
        safety_url="",
        devlogin_path=DEVLOGIN,
    )
    base.update(overrides)
    return Settings(**base)


@dataclass
class Harness:
    settings: Settings
    deps: AppDeps
    audit: FakeAudit
    fga: FakeFga
    sessions: FakeSessions
    clinical: FakeClinical
    client: httpx.AsyncClient

    async def login(self, login: str, *, on_duty: bool = True, auth_level: int = 1) -> dict:
        r = await self.client.post(
            "/auth/dev-login", json={"login": login, "on_duty": on_duty, "auth_level": auth_level}
        )
        assert r.status_code == 200, r.text
        return r.json()

    def new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.client._transport.app), base_url="http://test"
        )


def make_deps(
    settings: Settings, **overrides
) -> tuple[AppDeps, FakeAudit, FakeFga, FakeSessions, FakeClinical]:
    audit = overrides.get("audit") or FakeAudit()
    fga = overrides.get("fga") or FakeFga()
    sessions = overrides.get("sessions") or FakeSessions()
    clinical = overrides.get("clinical") or FakeClinical(demo_rows())
    notes = overrides.get("notes") or MemoryNotes(demo_note_chunks())
    objects = overrides.get("objects") or MemoryObjects()
    dicom = overrides.get("dicom")
    deps = AppDeps(
        settings=settings,
        audit=audit,
        audit_reader=audit,
        fga=fga,
        vault=StaticVault(VAULT, IDENTITIES),
        users=FakeUsers(),
        sessions=sessions,
        clinical=clinical,
        notes=notes,
        objects=objects,
        devlogin=DevLoginMap.load(settings.devlogin_path),
        dicom=dicom,
    )
    return deps, audit, fga, sessions, clinical


@pytest.fixture
async def harness() -> AsyncIterator[Harness]:
    settings = make_settings()
    deps, audit, fga, sessions, clinical = make_deps(settings)
    app = create_app(settings, deps)
    app.state.deps = deps  # lifespan is not run under ASGITransport
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield Harness(settings, deps, audit, fga, sessions, clinical, client)
