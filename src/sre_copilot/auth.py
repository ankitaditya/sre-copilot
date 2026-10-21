from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from sre_copilot.config import Settings

Role = Literal["viewer", "operator", "approver"]
ROLE_LEVEL = {"viewer": 0, "operator": 1, "approver": 2}
COOKIE_NAME = "sre_session"


@dataclass(frozen=True)
class Principal:
    id: str
    role: Role


@dataclass
class Session:
    principal: Principal
    csrf: str
    expires: float


class AuthManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, Session] = {}

    def token_principal(self, token: str) -> Principal | None:
        for candidate, role in self.settings.auth_tokens.items():
            if secrets.compare_digest(token.encode(), candidate.encode()):
                return Principal(hashlib.sha256(token.encode()).hexdigest()[:16], role)
        return None

    def session(self, request: Request) -> Session | None:
        identifier = request.cookies.get(COOKIE_NAME, "")
        session = self.sessions.get(identifier)
        if session and session.expires <= time.monotonic():
            del self.sessions[identifier]
            return None
        return session

    def authorize(self, request: Request, minimum: Role) -> Principal:
        if not self.settings.auth_enabled:
            return Principal("local-demo", "approver")
        header = request.headers.get("Authorization", "")
        if header:
            scheme, _, token = header.partition(" ")
            principal = self.token_principal(token) if scheme.lower() == "bearer" else None
        else:
            session = self.session(request)
            principal = session.principal if session else None
            if session and request.method not in {"GET", "HEAD", "OPTIONS"}:
                if not secrets.compare_digest(
                    request.headers.get("X-CSRF-Token", ""), session.csrf
                ):
                    raise HTTPException(403, "csrf_token_required")
        if principal is None:
            raise HTTPException(401, "authentication_required", headers={"WWW-Authenticate": "Bearer"})
        if ROLE_LEVEL[principal.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(403, "insufficient_role")
        request.state.principal = principal
        return principal


def require_role(role: Role) -> Callable[[Request], Awaitable[Principal]]:
    async def dependency(request: Request) -> Principal:
        try:
            principal = request.app.state.auth.authorize(request, role)
        except HTTPException as exc:
            await request.app.state.store.add_security_event("access_denied", str(exc.detail))
            raise
        run_id = request.path_params.get("run_id")
        if role != "viewer" and run_id:
            store = request.app.state.store
            if await store.get_run(run_id) is not None:
                await store.add_event(run_id, "operator_request", {
                    "actor": principal.id, "role": principal.role,
                    "operation": request.url.path.rsplit("/", 1)[-1],
                })
        return principal
    return dependency


router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    token: SecretStr = Field(min_length=1, max_length=4096)


@router.get("/session")
async def get_session(request: Request) -> dict[str, object]:
    auth: AuthManager = request.app.state.auth
    if not auth.settings.auth_enabled:
        return {"enabled": False, "authenticated": True, "role": "approver"}
    session = auth.session(request)
    return {
        "enabled": True, "authenticated": session is not None,
        "role": session.principal.role if session else None,
        "csrf_token": session.csrf if session else None,
    }


@router.post("/session")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, object]:
    auth: AuthManager = request.app.state.auth
    if not auth.settings.auth_enabled:
        raise HTTPException(409, "authentication_not_enabled")
    principal = auth.token_principal(payload.token.get_secret_value())
    if principal is None:
        await request.app.state.store.add_security_event("access_denied", "invalid_credentials")
        raise HTTPException(401, "invalid_credentials")
    auth.sessions = {
        key: value for key, value in auth.sessions.items() if value.expires > time.monotonic()
    }
    if len(auth.sessions) >= 1000:
        raise HTTPException(429, "session_limit_reached")
    identifier, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    auth.sessions[identifier] = Session(
        principal, csrf, time.monotonic() + auth.settings.session_ttl_seconds
    )
    await request.app.state.store.add_security_event("authentication", "session_created", principal.id)
    response.set_cookie(
        COOKIE_NAME, identifier, httponly=True, secure=auth.settings.auth_cookie_secure,
        samesite="strict", max_age=auth.settings.session_ttl_seconds, path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "enabled": True, "authenticated": True, "role": principal.role, "csrf_token": csrf,
    }


@router.delete("/session", dependencies=[Depends(require_role("viewer"))])
async def logout(request: Request, response: Response) -> dict[str, bool]:
    auth: AuthManager = request.app.state.auth
    auth.sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}
