"""Смысловой слой профиля: `profile_text` из графа и эмбеддинг через ml-api.

Текст строится детерминированно из проекций (роль, грейд, навыки) без ПДн. Вектор считается,
только если `sha256(profile_text)` отличается от сохранённого; такой же текст у другого
кандидата берётся из Redis (`c:emb:p:{model}:{sha}`).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

log = structlog.get_logger()

MAX_SKILLS = 30
CACHE_TTL_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True, slots=True)
class SkillLine:
    slug: str
    level: int
    confidence: float
    claimed_only: bool


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_profile_text(
    *,
    primary_role: str | None,
    roles: Sequence[tuple[str, float]],
    grade: str | None,
    experience_months: int | None,
    skills: Sequence[SkillLine],
) -> str:
    """Текст профиля. Подтверждённые навыки идут по убыванию доверия, заявленные — отдельно."""
    proven = sorted(
        (s for s in skills if not s.claimed_only and s.level > 0),
        key=lambda s: (-s.confidence, s.slug),
    )[:MAX_SKILLS]
    claimed = sorted(s.slug for s in skills if s.claimed_only)[:MAX_SKILLS]
    parts: list[str] = []
    if primary_role:
        parts.append(f"Роль: {primary_role}.")
    others = [r for r, _ in sorted(roles, key=lambda x: (-x[1], x[0])) if r != primary_role]
    if others:
        parts.append(f"Смежные роли: {', '.join(others[:3])}.")
    if grade:
        parts.append(f"Грейд: {grade}.")
    if experience_months:
        parts.append(f"Опыт: {experience_months // 12} лет {experience_months % 12} мес.")
    if proven:
        parts.append(
            "Подтверждённые навыки: " + ", ".join(f"{s.slug} ({s.level})" for s in proven) + "."
        )
    if claimed:
        parts.append(f"Заявленные навыки: {', '.join(claimed)}.")
    return " ".join(parts)


class EmbeddingError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Embedded:
    model: str
    vector: list[float]


class Embedder(Protocol):
    async def embed_passage(self, text: str) -> Embedded: ...


class MlEmbedder:
    """Клиент `POST /v1/embeddings` ml-api с кешем в Redis по sha текста."""

    def __init__(
        self,
        base_url: str,
        *,
        model: str = "BAAI/bge-m3",
        dim: int = 1024,
        timeout: float = 10.0,
        cooldown: float = 60.0,
        redis=None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = (
            model  # модель в ключе кеша; ответ ml-api с другой моделью кладётся под своим ключом
        )
        self._dim = dim
        self._redis = redis
        # после сбоя ml-api не долбим его на каждый пересчёт: пауза `cooldown` секунд
        self._cooldown = cooldown
        self._down_until = 0.0
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_passage(self, text: str) -> Embedded:
        sha = text_sha(text)
        if self._redis is not None:
            try:
                raw = await self._redis.get(f"c:emb:p:{self._model}:{sha}")
                if raw:
                    data = json.loads(raw)
                    return Embedded(data["model"], data["vector"])
            except Exception:  # кеш не критичен
                log.warning("embedding_cache_read_failed")
        if time.monotonic() < self._down_until:
            raise EmbeddingError("ml-api embeddings: пауза после сбоя")
        try:
            resp = await self._client.post(
                "/v1/embeddings", json={"texts": [text], "kind": "passage"}
            )
            resp.raise_for_status()
            body = resp.json()
            model, dim, vectors = body["model"], body["dim"], body["vectors"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._down_until = time.monotonic() + self._cooldown
            raise EmbeddingError(f"ml-api embeddings: {exc!r}") from exc
        if dim != self._dim or len(vectors) != 1 or len(vectors[0]) != self._dim:
            raise EmbeddingError(f"неожиданная размерность эмбеддинга: {dim}")
        result = Embedded(model, [float(x) for x in vectors[0]])
        if self._redis is not None:
            try:
                await self._redis.set(
                    f"c:emb:p:{model}:{sha}",
                    json.dumps({"model": model, "vector": result.vector}),
                    ex=CACHE_TTL_SECONDS,
                )
            except Exception:
                log.warning("embedding_cache_write_failed")
        return result
