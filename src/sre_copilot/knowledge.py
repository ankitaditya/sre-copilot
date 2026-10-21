from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from typing import Any

import httpx

from sre_copilot.config import Settings
from sre_copilot.models import RunState, RunStatus, utc_now
from sre_copilot.protection import DataProtection, PolicyViolation, bounded_request
from sre_copilot.store import RunStore

logger = logging.getLogger(__name__)


class KnowledgeIndex:
    def __init__(self, settings: Settings, store: RunStore):
        self.settings = settings
        self.store = store
        self.data = DataProtection(settings.auth_tokens)
        self._lock = asyncio.Lock()
        self.warnings: list[str] = []
        self._embedding_failed = False

    async def _embedding(self, text: str) -> list[float]:
        response = await bounded_request(
            "POST", f"{self.settings.ollama_base_url.rstrip('/')}/api/embed",
            allowed_origins=self.settings.allowed_model_origins,
            timeout=self.settings.tool_timeout_seconds,
            payload={"model": self.settings.knowledge_embedding_model, "input": text},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid_embedding_response")
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != 1:
            raise ValueError("invalid_embedding_response")
        vector = vectors[0]
        if (
            not isinstance(vector, list) or not 1 <= len(vector) <= 4096
            or not all(type(value) in {int, float} for value in vector)
        ):
            raise ValueError("invalid_embedding_vector")
        try:
            normalized = [float(value) for value in vector]
            norm = math.hypot(*normalized)
        except (OverflowError, ValueError) as exc:
            raise ValueError("invalid_embedding_vector") from exc
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("invalid_embedding_vector")
        return [value / norm for value in normalized]

    def _warn(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)
            logger.warning("Knowledge index: %s", code)

    async def _documents(
        self, kind: str, source: str, title: str, body: str, service: str,
        cached: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        try:
            source, title, body = (
                self.data.clean(source), self.data.clean(title), self.data.clean(body)
            )
        except PolicyViolation:
            self._warn("untrusted_document_quarantined")
            return []
        chunks = [
            body[offset:offset + self.settings.knowledge_chunk_size]
            for offset in range(0, len(body), self.settings.knowledge_chunk_size)
        ]
        documents = []
        for index, chunk in enumerate(chunks[:self.settings.knowledge_max_documents]):
            identifier = hashlib.sha256(f"{kind}:{source}:{index}".encode()).hexdigest()
            digest = hashlib.sha256(f"{title}\n{chunk}".encode()).hexdigest()
            old = cached.get(identifier, {})
            model, vector = "", []
            if self.settings.knowledge_embedding_model:
                if (
                    old.get("content_hash") == digest
                    and old.get("embedding_model") == self.settings.knowledge_embedding_model
                ):
                    model = old["embedding_model"]
                    vector = json.loads(old["embedding_json"])
                elif not self._embedding_failed:
                    try:
                        vector = await self._embedding(f"{title}\n{chunk}")
                        model = self.settings.knowledge_embedding_model
                    except (httpx.HTTPError, ValueError, TypeError):
                        self._embedding_failed = True
                        self._warn("embeddings_unavailable_using_full_text_search")
            documents.append({
                "id": identifier, "kind": kind, "source": source, "title": title,
                "body": chunk, "service": service, "content_hash": digest,
                "embedding_model": model, "embedding_json": json.dumps(vector),
                "updated_at": utc_now(),
            })
        return documents

    async def rebuild(self) -> dict[str, Any]:
        async with self._lock:
            self.warnings = []
            self._embedding_failed = False
            cached = {doc["id"]: doc for doc in await self.store.knowledge_documents()}
            documents = []
            directory = self.settings.runbooks_dir.resolve()
            if not directory.exists():
                self._warn("runbooks_directory_unavailable")
            else:
                for path in sorted(directory.glob("*.md")):
                    if path.is_symlink() or not path.is_file():
                        self._warn("runbook_symlink_skipped")
                        continue
                    if path.stat().st_size > 256_000:
                        self._warn("oversized_runbook_skipped")
                        continue
                    try:
                        text = path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError):
                        self._warn("unreadable_runbook_skipped")
                        continue
                    documents.extend(await self._documents(
                        "runbook", path.name, path.stem.replace("-", " "), text, "", cached
                    ))
                    if len(documents) >= self.settings.knowledge_max_documents:
                        self._warn("knowledge_capacity_reached")
                        break
            await self.store.replace_knowledge(
                "runbook", documents[:self.settings.knowledge_max_documents],
                self.settings.knowledge_max_documents,
            )
            for state in await self.store.resolved_runs(self.settings.knowledge_max_documents):
                await self._remember(state, cached)
        return await self.status()

    async def _remember(self, state: RunState, cached: dict[str, dict[str, Any]]) -> None:
        if state.status != RunStatus.RESOLVED:
            return
        text = json.dumps({
            "incident": state.description, "summary": state.summary,
            "findings": [{"title": item.title, "detail": item.detail} for item in state.findings],
            "completed_plan": [{"id": step.id, "notes": step.notes} for step in state.plan],
        }, ensure_ascii=False)
        documents = await self._documents(
            "incident", state.id, state.title, text, state.service, cached
        )
        for document in documents:
            document["updated_at"] = state.updated_at
        await self.store.replace_knowledge(
            "incident", documents, self.settings.knowledge_max_documents, source=state.id,
        )

    async def remember(self, state: RunState) -> None:
        async with self._lock:
            await self._remember(state, {})

    async def status(self) -> dict[str, Any]:
        documents = await self.store.knowledge_documents()
        return {
            "documents": len(documents),
            "runbook_chunks": sum(doc["kind"] == "runbook" for doc in documents),
            "incident_chunks": sum(doc["kind"] == "incident" for doc in documents),
            "embedding_model": self.settings.knowledge_embedding_model or None,
            "embedded_chunks": sum(bool(doc["embedding_model"]) for doc in documents),
            "warnings": self.warnings,
        }

    async def search(
        self, query: str, limit: int = 5, service: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        query = self.data.clean(query)[:2000]
        terms = re.findall(r"\w+", query, re.UNICODE)[:40]
        if not terms:
            return {"matches": [], "mode": "full_text", "warnings": list(self.warnings)}
        expression = " OR ".join(f'"{term}"' for term in terms)
        ranked = await self.store.search_knowledge(expression, self.settings.knowledge_max_documents)
        scores = {doc["id"]: 1 / (index + 1) for index, doc in enumerate(ranked)}
        candidates = {doc["id"]: doc for doc in ranked}
        mode = "full_text"
        if self.settings.knowledge_embedding_model and not self._embedding_failed:
            try:
                vector = await self._embedding(query)
                magnitude = math.sqrt(sum(value * value for value in vector))
                semantic_available = False
                for doc in await self.store.knowledge_documents():
                    if doc["embedding_model"] != self.settings.knowledge_embedding_model:
                        continue
                    stored = json.loads(doc["embedding_json"])
                    if len(stored) != len(vector):
                        self._warn("embedding_dimensions_changed_reindex_required")
                        continue
                    norm = math.sqrt(sum(value * value for value in stored))
                    semantic_available = semantic_available or norm > 0
                    similarity = sum(a * b for a, b in zip(vector, stored, strict=True)) / (
                        magnitude * norm
                    ) if norm else 0
                    if similarity > 0.2:
                        candidates[doc["id"]] = doc
                        scores[doc["id"]] = scores.get(doc["id"], 0) + similarity
                if semantic_available:
                    mode = "hybrid"
                else:
                    self._warn("no_embeddings_reindex_required")
            except (httpx.HTTPError, ValueError, TypeError):
                self._embedding_failed = True
                self._warn("embeddings_unavailable_using_full_text_search")
        matches = []
        for identifier in sorted(candidates, key=lambda key: scores[key], reverse=True):
            doc = candidates[identifier]
            if kind is not None and doc["kind"] != kind:
                continue
            if doc["service"] and doc["service"] not in self.settings.allowed_services:
                continue
            if service is not None and doc["service"] not in {"", service}:
                continue
            try:
                self.data.screen(doc["body"])
            except PolicyViolation:
                self._warn("untrusted_document_quarantined")
                continue
            matches.append({
                "id": identifier, "kind": doc["kind"], "source": doc["source"],
                "title": doc["title"], "excerpt": doc["body"][:1800],
                "score": round(scores[identifier], 4),
            })
            if len(matches) >= max(1, min(limit, 20)):
                break
        return {"matches": matches, "mode": mode, "warnings": list(self.warnings)}
