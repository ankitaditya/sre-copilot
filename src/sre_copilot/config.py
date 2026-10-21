from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    database_path: Path = Path("data/sre-copilot.db")
    ui_build_dir: Path = Path("ui/dist")
    runbooks_dir: Path = Path("runbooks")
    sandbox_state_path: Path = Path("sandbox/runtime/state.json")
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    llm_mode: Literal["auto", "ollama", "deterministic"] = "auto"
    max_steps: int = 12
    max_tool_calls: int = 24
    tool_timeout_seconds: float = 20
    cors_allow_origins: str = "http://localhost:5173"
    auth_enabled: bool = False
    auth_tokens: dict[str, Literal["viewer", "operator", "approver"]] = Field(
        default_factory=dict, repr=False
    )
    auth_cookie_secure: bool = False
    session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    allowed_services: list[str] = Field(default_factory=lambda: ["demo-api"])
    allowed_tools: list[str] = Field(default_factory=lambda: [
        "inspect_demo_service", "read_demo_logs", "search_runbooks", "search_knowledge",
        "http_healthcheck", "list_containers", "get_container_logs",
        "restore_demo_service", "restart_container",
    ])
    allowed_http_origins: list[str] = Field(default_factory=list)
    allowed_model_origins: list[str] = Field(default_factory=lambda: [
        "http://127.0.0.1:11434", "http://localhost:11434",
        "http://host.docker.internal:11434",
    ])
    knowledge_embedding_model: str = ""
    knowledge_max_documents: int = Field(default=2000, ge=1, le=10000)
    knowledge_chunk_size: int = Field(default=1800, ge=200, le=8000)

    @model_validator(mode="after")
    def validate_auth(self) -> Settings:
        if (self.auth_enabled and not self.auth_tokens) or any(
            len(token) < 32 for token in self.auth_tokens
        ):
            raise ValueError("Enabled authentication requires tokens of at least 32 characters.")
        if self.auth_enabled and any(
            origin.strip() in {"*", "null"} for origin in self.cors_allow_origins.split(",")
        ):
            raise ValueError("Authenticated access requires explicit trusted CORS origins.")
        for origin in [*self.allowed_http_origins, *self.allowed_model_origins]:
            try:
                parts = urlsplit(origin)
                port = parts.port
            except ValueError as exc:
                raise ValueError("Outbound allowlists must contain valid origins.") from exc
            if (
                parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.path not in {"", "/"} or parts.query or parts.fragment
                or port == 0
            ):
                raise ValueError("Outbound allowlists must contain origins without paths or credentials.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
