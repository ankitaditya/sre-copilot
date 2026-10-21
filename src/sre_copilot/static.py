from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def mount_spa(app: FastAPI, build_dir: Path) -> None:
    directory = build_dir.resolve()
    index = directory / "index.html"
    if not index.exists():
        logger.warning("UI build not found at %s", directory)

        async def fallback_page() -> HTMLResponse:
            return HTMLResponse(
                """
                <!doctype html><html><head><title>SRE Copilot</title></head>
                <body style="font-family:system-ui;max-width:720px;margin:4rem auto">
                <h1>SRE Copilot API is running</h1>
                <p>The operator UI has not been built. Run <code>cd ui && npm run build</code>.</p>
                <p><a href="/api/docs">Open API documentation</a></p>
                </body></html>
                """
            )

        app.add_api_route("/", fallback_page, include_in_schema=False)
        app.add_api_route(
            "/{full_path:path}",
            fallback_page,
            include_in_schema=False,
            name="ui-fallback-catch-all",
        )
        return

    assets = directory / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="ui-assets")

    for entry in directory.iterdir():
        if entry.is_file() and entry.name != "index.html":
            app.add_api_route(
                f"/{entry.name}",
                lambda path=entry: FileResponse(path),
                include_in_schema=False,
            )

    @app.get("/", include_in_schema=False)
    async def root() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str) -> FileResponse:
        del full_path
        return FileResponse(index)
