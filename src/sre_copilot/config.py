from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()

