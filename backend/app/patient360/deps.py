"""Dependency bundle. Real stores in production; fakes in tests via create_app(deps=...)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from .audit import AuditReader, AuditWriter, PgAuditWriter
from .auth.sessions import PgSessionStore, PgUserRepo, SessionManager, SessionStore, UserRepo
from .config import Settings
from .db import Database
from .devlogin import DevLoginMap
from .dicom import DicomStore, OrthancStore
from .fga import HttpFgaClient, RelationChecker
from .humanwrites import BreakGlassLimiter
from .nemo_rails import NemoRails
from .tools.reader import ClinicalReader, PgClinicalReader
from .tools.stores import HttpNotes, MemoryNotes, MemoryObjects, MinioObjects, NotesIndex, ObjectStore
from .vault import LinkageVault, OpenBaoVault


@dataclass
class AppDeps:
    settings: Settings
    audit: AuditWriter
    audit_reader: AuditReader
    fga: RelationChecker
    vault: LinkageVault
    users: UserRepo
    sessions: SessionStore
    clinical: ClinicalReader
    notes: NotesIndex
    objects: ObjectStore
    devlogin: DevLoginMap
    dicom: DicomStore | None = None
    nemo: NemoRails | None = None
    manager: SessionManager = field(init=False)
    break_glass_limiter: BreakGlassLimiter = field(init=False)
    closers: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.manager = SessionManager(
            settings=self.settings,
            users=self.users,
            sessions=self.sessions,
            vault=self.vault,
            audit=self.audit,
            devlogin=self.devlogin,
        )
        self.break_glass_limiter = BreakGlassLimiter(per_hour=self.settings.break_glass_per_hour)

        async def _retire_sandbox(sandbox_id: str) -> None:
            from .openshell import destroy_session_sandbox

            await destroy_session_sandbox(self.settings, sandbox_id)

        self.manager.on_sandbox_retire = _retire_sandbox

    @property
    def policy_version(self) -> str:
        return self.fga.policy_version

    async def close(self) -> None:
        for c in reversed(self.closers):
            await c()


async def build_deps(settings: Settings) -> AppDeps:
    db = Database(settings.db_dsn.get_secret_value())
    await db.open()

    fga = HttpFgaClient(
        settings.openfga_url, settings.openfga_key.get_secret_value(), settings.openfga_store_name
    )
    try:
        await fga.start()
    except Exception:
        await fga.close()
        await db.close()
        raise

    vault = OpenBaoVault(
        settings.linkage_url, settings.linkage_token.get_secret_value(), mount=settings.linkage_mount
    )
    audit = PgAuditWriter(db, agent_software=settings.agent_software, policy_version=fga.policy_version)

    notes: NotesIndex
    objects: ObjectStore
    if settings.qdrant_url:
        notes = HttpNotes(
            settings.qdrant_url,
            settings.qdrant_api_key.get_secret_value(),
            settings.embed_url,
            settings.embed_model,
        )
    else:
        notes = MemoryNotes()
    objects: ObjectStore = (
        MinioObjects(
            settings.minio_url,
            settings.minio_access_key,
            settings.minio_secret_key.get_secret_value(),
        )
        if settings.minio_url
        else MemoryObjects()
    )
    dicom: DicomStore | None = None
    if settings.orthanc_url:
        dicom = OrthancStore(
            settings.orthanc_url,
            settings.orthanc_user,
            settings.orthanc_password.get_secret_value(),
        )
    deps = AppDeps(
        settings=settings,
        audit=audit,
        audit_reader=audit,
        fga=fga,
        vault=vault,
        users=PgUserRepo(db),
        sessions=PgSessionStore(db),
        clinical=PgClinicalReader(db),
        notes=notes,
        objects=objects,
        devlogin=DevLoginMap.load(settings.devlogin_path),
        dicom=dicom,
    )
    deps.closers.extend([db.close, fga.close, vault.close])
    return deps


def get_deps(request: Request) -> AppDeps:
    return request.app.state.deps
