from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sre_copilot import __version__
from sre_copilot.api import router
from sre_copilot.config import Settings, get_settings
from sre_copilot.runtime import AgentRuntime
from sre_copilot.static import mount_spa
from sre_copilot.store import RunStore
from sre_copilot.tools import ToolRegistry

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = RunStore(settings.database_path)
        await store.initialize()
        tools = ToolRegistry(settings)
        runtime = AgentRuntime(settings, store, tools)
        app.state.store = store
        app.state.tools = tools
        app.state.runtime = runtime
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()
            store.close()

    application = FastAPI(
        title="SRE Copilot",
        version=__version__,
        description=(
            "Durable autonomous incident triage, approval-gated remediation, "
            "checkpoint history, and live operator events."
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)

    @application.get("/health", tags=["meta"])
    async def root_health() -> dict[str, str]:
        return {"status": "ok", "service": "sre-copilot", "version": __version__}

    mount_spa(application, settings.ui_build_dir)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "sre_copilot.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )
