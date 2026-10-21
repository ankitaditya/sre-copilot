from __future__ import annotations

import ipaddress
import re
import unicodedata
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

from sre_copilot.config import Settings

REDACTED = "[REDACTED]"


class PolicyViolation(ValueError):
    """A safe-to-display policy code, never the rejected content."""


class DataProtection:
    _sensitive_key = re.compile(
        r"(?:password|passwd|secret|authorization|api[_-]?key|access[_-]?token|"
        r"refresh[_-]?token|private[_-]?key|ssn|credit[_-]?card)", re.I
    )
    _patterns = [
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
                   r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.S),
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                   r"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})\b"),
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.I),
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)"
                   r"\s*[=:]\s*[\"']?[^\s,\"';}]+[\"']?"),
        re.compile(r"(?i)(?<=://)[^/\s:@]+:[^/\s@]+@"),
        re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ]
    _injection = [
        r"\b(?:ignore|disregard|override)\b.{0,60}\b(?:previous|prior|system|developer|"
        r"safety|all)\b.{0,40}\b(?:instructions?|rules?|prompts?|polic(?:y|ies))\b",
        r"\b(?:bypass|disable|skip)\b.{0,50}\b(?:approval|security|safety|guardrails?|"
        r"authentication|dlp)\b",
        r"\b(?:reveal|print|show|leak|exfiltrate|send)\b.{0,70}\b"
        r"(?:system prompt|developer prompt|secrets?|credentials?|api keys?|access tokens?)\b",
        r"<\|(?:im_start|im_end|system|assistant|endoftext)\|>|\[/?INST\]|"
        r"<<SYS>>|</?(?:system|developer|assistant)>",
        r"\b(?:you are now|act as)\b.{0,40}\b(?:system|developer|unrestricted|jailbroken)\b",
    ]

    def __init__(self, secrets: Iterable[str] = ()):
        self._secrets = tuple(secret for secret in secrets if isinstance(secret, str) and secret)

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): REDACTED if self._sensitive_key.search(str(key)) else self.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, REDACTED)
            for pattern in self._patterns:
                value = pattern.sub(REDACTED, value)
            value = re.sub(
                r"(?<![\w.-])(?:\d[ -]?){12,18}\d(?![\w.-])",
                self._redact_card, value,
            )
        return value

    @staticmethod
    def _redact_card(match: re.Match[str]) -> str:
        digits = [int(char) for char in match.group() if char.isdigit()]
        if len(set(digits)) < 2:
            return match.group()
        checksum = 0
        for index, digit in enumerate(reversed(digits)):
            if index % 2:
                digit *= 2
                digit = digit - 9 if digit > 9 else digit
            checksum += digit
        return REDACTED if checksum % 10 == 0 else match.group()

    def screen(self, value: Any) -> None:
        def text_parts(item: Any) -> Iterable[str]:
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                for key, child in item.items():
                    yield str(key)
                    yield from text_parts(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    yield from text_parts(child)

        text = unicodedata.normalize("NFKC", "\n".join(text_parts(value)))
        text = "".join(char for char in text if unicodedata.category(char) != "Cf")
        for pattern in self._injection:
            for match in re.finditer(pattern, text, re.I | re.S):
                prefix = text[max(0, match.start() - 24):match.start()]
                if re.search(r"\b(?:never|do not|don't|must not|should not)\s+$", prefix, re.I):
                    continue
                raise PolicyViolation("prompt_injection_detected")

    def clean(self, value: Any) -> Any:
        self.screen(value)
        return self.redact(value)


class GovernancePolicy:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.data = DataProtection(settings.auth_tokens)

    def service(self, service: str) -> None:
        if service not in self.settings.allowed_services:
            raise PolicyViolation("service_not_allowed")

    def tool(self, name: str, args: dict[str, Any], service: str | None = None) -> None:
        if name not in self.settings.allowed_tools:
            raise PolicyViolation("tool_not_allowed")
        self.data.screen(args)
        if self.data.redact(args) != args:
            raise PolicyViolation("sensitive_tool_arguments")
        if service is not None:
            self.service(service)
        if name in {"restart_container", "get_container_logs"}:
            target = str(args.get("name", ""))
            self.service(target)
            if service is not None and target != service:
                raise PolicyViolation("cross_service_target_blocked")
        if name in {"inspect_demo_service", "read_demo_logs", "restore_demo_service"}:
            self.service("demo-api")
            if service is not None and service != "demo-api":
                raise PolicyViolation("cross_service_target_blocked")
        if name == "http_healthcheck":
            self.url(str(args.get("url", "")), self.settings.allowed_http_origins)

    @staticmethod
    def url(url: str, allowed_origins: list[str]) -> str:
        try:
            parts = urlsplit(url)
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError as exc:
            raise PolicyViolation("invalid_outbound_url") from exc
        if (
            parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None or parts.fragment
        ):
            raise PolicyViolation("invalid_outbound_url")
        host = parts.hostname.lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address and (address.is_link_local or address.is_unspecified or address.is_multicast):
            raise PolicyViolation("outbound_address_blocked")
        if host in {"metadata.google.internal", "instance-data"}:
            raise PolicyViolation("outbound_address_blocked")
        origin = (parts.scheme, host, port)
        allowed = []
        for value in allowed_origins:
            configured = urlsplit(value)
            allowed.append((
                configured.scheme, configured.hostname,
                configured.port or (443 if configured.scheme == "https" else 80),
            ))
        if origin not in allowed:
            raise PolicyViolation("outbound_origin_not_allowed")
        return url


async def bounded_request(
    method: str, url: str, *, allowed_origins: list[str], timeout: float,
    payload: dict[str, Any] | None = None, max_bytes: int = 1_048_576,
) -> httpx.Response:
    GovernancePolicy.url(url, allowed_origins)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        async with client.stream(method, url, json=payload) as response:
            if response.is_redirect:
                raise PolicyViolation("outbound_redirect_blocked")
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise PolicyViolation("outbound_response_too_large")
            return httpx.Response(
                response.status_code, headers={
                    key: value for key, value in response.headers.items()
                    if key.lower() not in {"content-encoding", "content-length"}
                },
                content=bytes(content), request=response.request,
            )
