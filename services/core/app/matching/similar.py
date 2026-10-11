"""Похожие кандидаты: пересечение навыков с весом по доверию + вектор.

`sim = W_SKILLS · J + W_VECTOR · cos⁺`, где `J = Σ min(c_a, c_b) / Σ max(c_a, c_b)` по навыкам
без `claimed_only`, `cos⁺` — косинус эмбеддингов, обрезанный снизу нулём. Нет вектора у одной из
сторон — берём только `J`. Работодатель видит только анонимные `CandidateCard`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.trust import TrustConfig
from app.matching import search
from app.matching.scoring import cosine
from app.matching.service import only_visible
from app.taxonomy import service as taxonomy

W_SKILLS = 0.7
W_VECTOR = 0.3
MIN_SIMILARITY = 0.05
MAX_LIMIT = 20


class SimilarCard(search.CandidateCard):
    similarity: float
    common_skills: list[str]


def skill_overlap(a: dict[Any, float], b: dict[Any, float]) -> float:
    """Взвешенный Жаккар по доверию: 0 — нет общих навыков, 1 — одинаковые."""
    keys = a.keys() | b.keys()
    den = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    if den <= 0:
        return 0.0
    return sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys) / den


def similarity(
    a: dict[Any, float],
    b: dict[Any, float],
    va: Sequence[float] | None,
    vb: Sequence[float] | None,
) -> float:
    """Похожесть кандидатов: `W_SKILLS·J + W_VECTOR·cos⁺`; без вектора у одной из сторон — только
    `J`.
    """
    j = skill_overlap(a, b)
    if va is None or vb is None or len(va) == 0 or len(vb) == 0 or len(va) != len(vb):
        return round(j, 6)
    return round(W_SKILLS * j + W_VECTOR * max(0.0, cosine(va, vb)), 6)


def _held(skills: list[Any]) -> dict[uuid.UUID, float]:
    return {s.skill_id: float(s.confidence) for s in skills if not s.claimed_only}


async def find_similar(
    session: AsyncSession,
    base: Candidate,
    *,
    company_id: uuid.UUID,
    trust: TrustConfig,
    limit: int = 10,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Топ похожих на `base` среди видимых этой компании анкет (сам кандидат исключён)."""
    limit = max(1, min(limit, MAX_LIMIT))
    day = today or datetime.now(UTC).date()
    pool = [
        c
        for c in await only_visible(
            session, await candidates.search_pool(session, company_id=company_id)
        )
        if c.user_id != base.user_id
    ]
    if not pool:
        return []
    owned = await graph.all_skills_of(session, [base.user_id, *(c.user_id for c in pool)])
    mine = _held(owned[base.user_id])
    scored: list[tuple[float, Candidate]] = []
    for c in pool:
        s = similarity(mine, _held(owned[c.user_id]), base.embedding, c.embedding)
        if s >= MIN_SIMILARITY:
            scored.append((s, c))
    scored.sort(key=lambda t: (-t[0], t[1].pseudo_id))
    top = scored[:limit]
    if not top:
        return []
    ids = [c.user_id for _, c in top]
    sids = {s.skill_id for u in ids for s in owned[u]} | set(mine)
    briefs = await taxonomy.skill_briefs(session, list(sids))
    names = {sid: (b[0], b[1]) for sid, b in briefs.items()}
    hl = await search._fsp_highlights(session, ids, trust, day)
    cats = await search.categories_of(session, ids)
    out: list[dict[str, Any]] = []
    for s, c in top:
        common = sorted(
            names[k][1] for k in mine.keys() & _held(owned[c.user_id]).keys() if k in names
        )
        card = search._card(
            c, owned[c.user_id], names, hl.get(c.user_id, []), None,
            categories=cats.get(c.user_id, []),
        )  # fmt: skip
        out.append(
            SimilarCard(**card.model_dump(), similarity=s, common_skills=common).model_dump(
                mode="json"
            )
        )
    return out
