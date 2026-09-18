"""FastAPI app factory. Run with: uvicorn --factory patient360.main:create_app"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .auth.router import router as auth_router
from .config import Settings
from .deps import AppDeps, build_deps
from .errors import install_handlers
from .media import router as media_router
from .routers.appointments import router as appointments_router
from .routers.audit import router as audit_router
from .routers.break_glass import router as break_glass_router
from .routers.chat import router as chat_router
from .routers.consents import router as consents_router
from .routers.dev import router as dev_router
from .routers.identity import router as identity_router
from .routers.me import router as me_router
from .routers.redteam import router as redteam_router
from .routers.uploads import router as uploads_router
from .tools.router import router as tools_router

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, deps: AppDeps | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = deps is None
        app.state.deps = deps or await build_deps(settings)
        log.info(
            "patient360 backend up: policy_version=%s dev=%s", app.state.deps.policy_version, settings.dev
        )
        try:
            yield
        finally:
            if owned:
                await app.state.deps.close()

    app = FastAPI(
        title="Patient360 backend",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.dev else None,
    )
    install_handlers(app)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(tools_router)
    app.include_router(consents_router)
    app.include_router(break_glass_router)
    app.include_router(identity_router)
    app.include_router(appointments_router)
    app.include_router(audit_router)
    app.include_router(chat_router)
    app.include_router(media_router)
    app.include_router(uploads_router)
    app.include_router(redteam_router)
    app.include_router(dev_router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "policy_version": app.state.deps.policy_version}

    return app
