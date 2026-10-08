"""Индекс графа навыков в ml и быстрый путь `/v1/skills/resolve` (skills.md §3, шаги 1–3).

Нормализация → точный поиск по синонимам → нечёткий поиск (rapidfuzz ≥ 92).
Модерация, судья и решения о новых вершинах — `skill_pipeline.py` (E16-4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from fsp_contracts.ml import SkillMention, SkillResolveItem
from rapidfuzz import fuzz, process

from fsp_ml.normalize import light, normalize, variants

log = structlog.get_logger()

FUZZY_THRESHOLD = 92.0
FUZZY_MIN_LEN = 4  # короткие строки («go», «c», «r») нечётко не ищем: слишком много ложных


@dataclass
class TaxonomyIndex:
    version: int = 0
    exact: dict[str, str] = field(default_factory=dict)  # норм. синоним → slug
    kinds: dict[str, str] = field(default_factory=dict)  # slug → kind
    names: dict[str, str] = field(default_factory=dict)  # slug → название
    aliases: dict[str, list[str]] = field(default_factory=dict)  # slug → синонимы
    statuses: dict[str, str] = field(default_factory=dict)  # slug → active | provisional
    distinct: set[frozenset[str]] = field(default_factory=set)  # «точно разные» (skill_distinct)
    _fuzzy_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any]) -> TaxonomyIndex:
        idx = cls(version=int(snap.get("version", 0)))
        for s in snap.get("skills", []):
            slug = s["slug"]
            idx.kinds[slug] = s.get("kind", "hard")
            idx.names[slug] = s.get("name") or slug
            idx.aliases[slug] = list(s.get("aliases", []))
            idx.statuses[slug] = s.get("status", "active")
            for name in (slug, s.get("name") or "", *s.get("aliases", [])):
                key = light(name)
                if key:
                    idx.exact.setdefault(key, slug)
        for pair in snap.get("distinct", []):
            if len(pair) == 2:
                idx.distinct.add(frozenset(pair))
        idx._fuzzy_keys = sorted(idx.exact)
        return idx

    def lookup(self, raw: str) -> str | None:
        for v in variants(raw):
            if v in self.exact:
                return self.exact[v]
        return None

    def fuzzy(self, raw: str) -> str | None:
        norm = normalize(raw)
        if len(norm) < FUZZY_MIN_LEN:
            return None
        hits = process.extract(
            norm, self._fuzzy_keys, scorer=fuzz.ratio, score_cutoff=FUZZY_THRESHOLD, limit=5
        )
        slugs = list(dict.fromkeys(self.exact[k] for k, _, _ in hits))
        if len(slugs) != 1:
            # пусто или неоднозначно (например, близко к обеим вершинам пары skill_distinct)
            return None
        return slugs[0]

    def resolve(self, m: SkillMention) -> SkillResolveItem | None:
        """None — быстрый путь не нашёл, нужен остальной конвейер."""
        norm = normalize(m.raw)
        slug = self.lookup(m.raw)
        decision = "alias"
        if slug is None:
            slug = self.fuzzy(m.raw)
            decision = "fuzzy"
        if slug is None:
            return None
        return SkillResolveItem(
            raw=m.raw,
            norm=norm,
            decision=decision,  # type: ignore[arg-type]
            skill_slug=slug,
            kind=self.kinds.get(slug, "hard"),  # type: ignore[arg-type]
        )


class TaxonomyProvider:
    """Держит индекс; при другой `taxonomy_version` в запросе перечитывает снимок из core."""

    def __init__(self, core_url: str, token: str, ttl: float = 30.0) -> None:
        self._url = core_url.rstrip("/") + "/internal/taxonomy/snapshot"
        self._token = token
        self._ttl = ttl
        self._index: TaxonomyIndex | None = None
        self._loaded_at = 0.0

    def set_snapshot(self, snap: dict[str, Any]) -> None:
        self._index = TaxonomyIndex.from_snapshot(snap)
        self._loaded_at = time.monotonic()

    async def get(self, wanted_version: int) -> TaxonomyIndex | None:
        idx = self._index
        fresh = idx is not None and idx.version >= wanted_version
        if fresh or (idx and time.monotonic() - self._loaded_at < self._ttl):
            return idx
        if not (self._url and self._token):
            return idx
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(self._url, headers={"Authorization": f"Service {self._token}"})
                r.raise_for_status()
            self.set_snapshot(r.json())
        except (httpx.HTTPError, ValueError):
            log.warning("taxonomy_snapshot_unavailable")
            self._loaded_at = time.monotonic()  # не долбим core на каждый запрос
        return self._index
