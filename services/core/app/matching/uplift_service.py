"""Uplift кандидата: данные, кеш, способы подтверждения."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.trust import TrustConfig
from app.matching.scoring import MatchConfig, Requirement, VacancyView
from app.matching.service import build_views
from app.matching.uplift import UpliftConfig, UpliftResult, is_relevant, simulate, top_roles
from app.taxonomy import service as taxonomy
from app.vacancies import service as vacancies

CACHE_TTL = 600  # 10 минут


def empty(base: int = 0, total: int = 0) -> dict[str, Any]:
    return {"relevant_total": total, "base": base, "items": [], "combo": None}


async def _how_to_confirm(
    session: AsyncSession,
    cand: Candidate,
    res: UpliftResult,
    cfg: UpliftConfig,
    today: date,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    ids = [g.skill_id for g in res.items]
    testable = await taxonomy.testable_ids(session, ids)
    has_code = bool(ids) and await graph.has_source(session, cand.user_id, "github")
    comps = await graph.upcoming_competitions(session, today, cfg.competition_days) if ids else []
    rules = await taxonomy.discipline_rules(session) if comps else {}
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for sid in ids:
        how: list[dict[str, Any]] = []
        if sid in testable:
            how.append({"kind": "test", "minutes": cfg.test_minutes})
        if has_code:
            how.append({"kind": "github"})
        for c in comps:  # skill ← rule ← discipline ← competition
            hit = any(
                r.skill_id == sid and r.weight >= cfg.competition_min_weight
                for r in rules.get(c.discipline or "", ())
            )
            if hit and c.start_date is not None:
                item: dict[str, Any] = {
                    "kind": "fsp_competition", "id": c.id, "title": c.title or c.id,
                    "start_date": c.start_date.isoformat(),
                }  # fmt: skip
                if c.registration_url:
                    item["registration_url"] = c.registration_url
                how.append(item)
        out[sid] = how
    return out


async def compute(
    session: AsyncSession,
    redis: Any,
    cand: Candidate,
    cfg: MatchConfig,
    trust: TrustConfig,
    ucfg: UpliftConfig | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Uplift кандидата: какие навыки добавят больше всего релевантных вакансий, с кешем в Redis."""
    ucfg = ucfg or UpliftConfig.load()
    day = today or datetime.now(UTC).date()
    published = await vacancies.list_published(session)
    # ключ кеша: (profile_version, версии вакансий) — любое изменение сбрасывает прежний ответ
    stamp = hashlib.sha1(  # noqa: S324 — не криптография
        "|".join(sorted(f"{v.id}:{v.version}" for v in published)).encode()
    ).hexdigest()[:16]
    key = f"c:uplift:{cand.user_id}:{cand.profile_version}:{stamp}:{day.isoformat()}"
    if redis is not None:
        try:
            if (hit := await redis.get(key)) is not None:
                return json.loads(hit)
        except Exception:  # noqa: BLE001 — кеш не должен ронять ответ
            pass

    out = await _compute(session, cand, published, cfg, trust, ucfg, day)
    if redis is not None:
        try:
            await redis.set(key, json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    return out


async def _compute(
    session: AsyncSession,
    cand: Candidate,
    published: list,
    cfg: MatchConfig,
    trust: TrustConfig,
    ucfg: UpliftConfig,
    day: date,
) -> dict[str, Any]:
    if not published or cand.deleted_at is not None:
        return empty()
    skills_by_v = await vacancies.skills_of(session, [v.id for v in published])
    all_ids = list(dict.fromkeys(vs.skill_id for rows in skills_by_v.values() for vs, _ in rows))
    adj = await taxonomy.adjacency(session, all_ids)
    names = await taxonomy.skill_names(session, all_ids)
    skill_graph = await taxonomy.load_skill_graph(session)
    names = {**names, **{k: skill_graph.slugs[k] for k in skill_graph.slugs if k not in names}}

    # проекция кандидата строим один раз по объединению навыков всех вакансий
    union = tuple(
        Requirement(s, names.get(s, str(s)), names.get(s, str(s)), False) for s in all_ids
    )
    shell = VacancyView(uuid.uuid4(), 0, uuid.uuid4(), "intern", "lead", (), 0, 0, union)
    (view,) = await build_views(session, [cand], shell, adj, trust, day)

    roles = top_roles(cand.roles, cand.primary_role)
    relevant: list[VacancyView] = []
    for v in published:
        reqs = tuple(
            Requirement(vs.skill_id, slug, names.get(vs.skill_id, slug), vs.required,
                        vs.min_level, vs.weight)
            for vs, slug in skills_by_v[v.id]
        )  # fmt: skip
        vv = VacancyView(
            id=v.id, version=v.version, company_id=v.company_id, grade_min=v.grade_min,
            grade_max=v.grade_max, formats=tuple(v.formats or ()), salary_from=v.salary_from,
            salary_to=v.salary_to, skills=reqs,
            important_qualities=tuple(v.important_qualities or ()),
        )  # fmt: skip
        if is_relevant(vv, v.role, roles, view, ucfg):
            relevant.append(vv)

    res = simulate(relevant, view, adj, names, skill_graph.parents_of, cfg, trust, ucfg)
    how = await _how_to_confirm(session, cand, res, ucfg, day)
    briefs = {g.skill_id: names.get(g.skill_id, str(g.skill_id)) for g in res.items}
    slugs = await taxonomy.skill_slugs(session, list({*briefs, *res.combo_ids}))
    items = [
        {
            "skill": slugs.get(g.skill_id, str(g.skill_id)),
            "name": briefs[g.skill_id],
            "current_level": (view.skills[g.skill_id].level if g.skill_id in view.skills else 0),
            "extra": g.extra,
            "pct": g.pct,
            "median_salary_delta": g.median_salary_delta,
            "how_to_confirm": how.get(g.skill_id, []),
        }
        for g in res.items
    ]
    combo = None
    if len(res.combo_ids) >= 2:
        combo = {
            "skills": [slugs.get(s, str(s)) for s in res.combo_ids],
            "extra": res.combo_extra,
            "pct": res.combo_pct,
        }
    return {"relevant_total": res.relevant_total, "base": res.base, "items": items, "combo": combo}
