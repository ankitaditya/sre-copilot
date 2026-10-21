from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sre_copilot import __version__
from sre_copilot.api import router
from sre_copilot.auth import AuthManager
from sre_copilot.auth import router as auth_router
from sre_copilot.config import Settings, get_settings
from sre_copilot.protection import DataProtection, PolicyViolation
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
        store = RunStore(settings.database_path, DataProtection(settings.auth_tokens))
        await store.initialize()
        tools = ToolRegistry(settings)
        runtime = AgentRuntime(settings, store, tools)
        app.state.store = store
        app.state.tools = tools
        app.state.runtime = runtime
        app.state.auth = AuthManager(settings)
        try:
            await runtime.start()
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
    origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    application.include_router(auth_router)

    @application.exception_handler(PolicyViolation)
    async def policy_error(request: Request, exc: PolicyViolation) -> JSONResponse:
        principal = getattr(request.state, "principal", None)
        await request.app.state.store.add_security_event(
            "policy_denied", str(exc), principal.id if principal else "anonymous"
        )
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request
        return JSONResponse(status_code=422, content={
            "detail": [{"type": error["type"], "loc": error["loc"]} for error in exc.errors()]
        })

    @application.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

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
