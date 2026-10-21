from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sre_copilot.app import create_app
from sre_copilot.config import Settings


def test_health_tools_and_spa_fallback(tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "service": "demo-api",
                "fault": "none",
                "symptoms": [],
                "logs": [],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        environment="test",
        database_path=tmp_path / "api.db",
        sandbox_state_path=state_path,
        runbooks_dir=tmp_path,
        ui_build_dir=tmp_path / "missing",
        llm_mode="deterministic",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/health").json()["runtime"] == "ready"
        tools = client.get("/api/tools").json()
        assert any(tool["name"] == "restore_demo_service" for tool in tools)
        assert client.get("/").status_code == 200
        assert "SRE Copilot API is running" in client.get("/").text
        assert "SRE Copilot API is running" in client.get("/operator/runs/example").text
        assert "SRE Copilot API is running" in client.get("/api/not-a-real-route").text
