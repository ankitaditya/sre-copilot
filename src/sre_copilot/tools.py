from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from sre_copilot.config import Settings
from sre_copilot.models import ToolDefinition, utc_now

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistry:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._tools: dict[str, RegisteredTool] = {}
        self._register_defaults()

    def _register(
        self,
        name: str,
        description: str,
        risk: Literal["read_only", "mutating"],
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        self._tools[name] = RegisteredTool(
            ToolDefinition(
                name=name,
                description=description,
                risk=risk,
                input_schema=input_schema,
            ),
            handler,
        )

    def _register_defaults(self) -> None:
        self._register(
            "inspect_demo_service",
            "Read the portable demo service state and active fault.",
            "read_only",
            {"type": "object", "properties": {}},
            self._inspect_demo_service,
        )
        self._register(
            "read_demo_logs",
            "Read recent demo service log entries.",
            "read_only",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            },
            self._read_demo_logs,
        )
        self._register(
            "search_runbooks",
            "Search local operational runbooks for relevant procedures.",
            "read_only",
            {
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
            self._search_runbooks,
        )
        self._register(
            "http_healthcheck",
            "Call an HTTP health endpoint and return status and latency.",
            "read_only",
            {
                "type": "object",
                "required": ["url"],
                "properties": {"url": {"type": "string", "format": "uri"}},
            },
            self._http_healthcheck,
        )
        self._register(
            "list_containers",
            "List local Docker containers when Docker is available.",
            "read_only",
            {"type": "object", "properties": {}},
            self._list_containers,
        )
        self._register(
            "get_container_logs",
            "Read bounded logs from a local Docker container.",
            "read_only",
            {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "tail": {"type": "integer", "minimum": 1, "maximum": 500},
                },
            },
            self._get_container_logs,
        )
        self._register(
            "restore_demo_service",
            "Clear the injected demo fault and restore the service configuration.",
            "mutating",
            {
                "type": "object",
                "properties": {
                    "expected_fault": {"type": "string"},
                    "change_ticket": {"type": "string"},
                },
            },
            self._restore_demo_service,
        )
        self._register(
            "restart_container",
            "Restart one local Docker container.",
            "mutating",
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
            self._restart_container,
        )

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def get(self, name: str) -> RegisteredTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        try:
            result = await asyncio.wait_for(
                tool.handler(args), timeout=self._settings.tool_timeout_seconds
            )
            return {"ok": True, "data": result}
        except TimeoutError:
            return {"ok": False, "error": "tool_timeout", "retryable": True}
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc), "retryable": False}
        except (OSError, httpx.HTTPError) as exc:
            return {"ok": False, "error": str(exc), "retryable": True}

    async def _inspect_demo_service(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        state = self._load_sandbox_state()
        return {
            "service": state.get("service", "demo-api"),
            "healthy": state.get("fault", "none") == "none",
            "fault": state.get("fault", "none"),
            "symptoms": state.get("symptoms", []),
            "last_changed_at": state.get("last_changed_at"),
        }

    async def _read_demo_logs(self, args: dict[str, Any]) -> dict[str, Any]:
        state = self._load_sandbox_state()
        limit = max(1, min(int(args.get("limit", 80)), 200))
        logs = state.get("logs", [])
        return {"lines": logs[-limit:], "truncated": len(logs) > limit}

    async def _search_runbooks(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_-]+", query) if len(term) > 2}
        matches: list[dict[str, Any]] = []
        if not self._settings.runbooks_dir.exists():
            return {"matches": [], "notice": "runbooks directory is not available"}
        for path in sorted(self._settings.runbooks_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            score = sum(text.lower().count(term) for term in terms)
            if score:
                excerpt = " ".join(text.split())[:700]
                matches.append({"path": str(path), "score": score, "excerpt": excerpt})
        matches.sort(key=lambda item: item["score"], reverse=True)
        return {"matches": matches[:5]}

    async def _http_healthcheck(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must use http or https")
        async with httpx.AsyncClient(timeout=self._settings.tool_timeout_seconds) as client:
            response = await client.get(url)
        return {
            "url": url,
            "status_code": response.status_code,
            "healthy": response.is_success,
            "body": response.text[:2000],
        }

    async def _list_containers(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        output = await self._docker(
            "ps", "--format", "{{json .}}"
        )
        containers = [json.loads(line) for line in output.splitlines() if line.strip()]
        return {"containers": containers}

    async def _get_container_logs(self, args: dict[str, Any]) -> dict[str, Any]:
        name = self._safe_container_name(args.get("name"))
        tail = max(1, min(int(args.get("tail", 100)), 500))
        output = await self._docker("logs", "--tail", str(tail), name)
        return {"name": name, "logs": output[-20000:], "truncated": len(output) > 20000}

    async def _restore_demo_service(self, args: dict[str, Any]) -> dict[str, Any]:
        state = self._load_sandbox_state()
        expected = args.get("expected_fault")
        current = state.get("fault", "none")
        if expected and expected != current:
            raise ValueError(f"fault changed from {expected!r} to {current!r}; refusing stale action")
        state["fault"] = "none"
        state["symptoms"] = []
        state["last_changed_at"] = utc_now()
        state.setdefault("logs", []).append(
            f"{utc_now()} INFO remediation applied; service configuration restored"
        )
        self._save_sandbox_state(state)
        return {
            "changed": True,
            "previous_fault": current,
            "change_ticket": args.get("change_ticket"),
            "healthy": True,
        }

    async def _restart_container(self, args: dict[str, Any]) -> dict[str, Any]:
        name = self._safe_container_name(args.get("name"))
        output = await self._docker("restart", name)
        return {"name": name, "output": output.strip()}

    def _load_sandbox_state(self) -> dict[str, Any]:
        path = self._settings.sandbox_state_path
        if not path.exists():
            raise OSError(
                f"Sandbox state not found at {path}. Run `python sandbox/chaos.py reset`."
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_sandbox_state(self, state: dict[str, Any]) -> None:
        path = self._settings.sandbox_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _safe_container_name(value: Any) -> str:
        name = str(value or "")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
            raise ValueError("invalid container name")
        return name

    @staticmethod
    async def _docker(*arguments: str) -> str:
        process = await asyncio.create_subprocess_exec(
            "docker",
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode:
            raise OSError(stderr.decode(errors="replace").strip() or "docker command failed")
        return stdout.decode(errors="replace")
